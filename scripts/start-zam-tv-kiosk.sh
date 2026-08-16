#!/bin/bash

set -u

APP_URL="http://127.0.0.1/screen"
HEALTH_URL="http://127.0.0.1/screen/health"
STATE_DIR="$HOME/.local/state"
LOG_FILE="$STATE_DIR/zam-tv-kiosk.log"
PROFILE_DIR="$STATE_DIR/zam-tv-chromium-profile"
CHECK_INTERVAL_SECONDS=15
START_GRACE_SECONDS=30

mkdir -p "$STATE_DIR" "$PROFILE_DIR"

# Je nach Raspberry-Pi-OS-Version heisst das Programm unterschiedlich.
if command -v chromium > /dev/null; then
  CHROMIUM="chromium"
elif command -v chromium-browser > /dev/null; then
  CHROMIUM="chromium-browser"
else
  echo "Chromium wurde nicht gefunden." >&2
  exit 1
fi

log_message() {
  echo "$(date '+%Y-%m-%d %H:%M:%S') $1" >> "$LOG_FILE"
}

stop_chromium() {
  local browser_pid="$1"

  kill "$browser_pid" 2> /dev/null || true
  for _ in $(seq 1 10); do
    if ! kill -0 "$browser_pid" 2> /dev/null; then
      wait "$browser_pid" 2> /dev/null || true
      return
    fi
    sleep 1
  done

  # Nur die von diesem Skript gestartete Chromium-Instanz hart beenden.
  pkill -KILL -f -- "--user-data-dir=$PROFILE_DIR" 2> /dev/null || true
  wait "$browser_pid" 2> /dev/null || true
}

# Eine eventuell uebrig gebliebene Instanz mit unserem eigenen Profil beenden.
pkill -TERM -f -- "--user-data-dir=$PROFILE_DIR" 2> /dev/null || true

while true; do
  # Auf die Flask-App im Docker-Container warten.
  until curl -fsS --max-time 5 "$APP_URL" > /dev/null; do
    sleep 2
  done

  "$CHROMIUM" \
    "$APP_URL" \
    --kiosk \
    --ozone-platform=wayland \
    --start-maximized \
    --noerrdialogs \
    --disable-infobars \
    --lang=de-DE \
    --no-first-run \
    --disable-session-crashed-bubble \
    --check-for-update-interval=31536000 \
    --password-store=basic \
    --user-data-dir="$PROFILE_DIR" \
    >> "$LOG_FILE" 2>&1 &
  browser_pid=$!
  log_message "Chromium wurde gestartet (PID $browser_pid)."

  # Der erste Seitenaufbau darf kurz dauern, ohne den Watchdog auszuloesen.
  sleep "$START_GRACE_SECONDS"

  while kill -0 "$browser_pid" 2> /dev/null; do
    health_status=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2> /dev/null) || health_status="000"

    if [ "$health_status" = "503" ]; then
      log_message "Seit mehr als 10 Minuten kein Bildschirmfortschritt; Chromium wird neu gestartet."
      stop_chromium "$browser_pid"
      break
    fi

    # Bei 000 oder einem App-Fehler warten wir auf Flask, statt Chromium neu zu starten.
    sleep "$CHECK_INTERVAL_SECONDS"
  done

  if kill -0 "$browser_pid" 2> /dev/null; then
    stop_chromium "$browser_pid"
  else
    wait "$browser_pid" 2> /dev/null || true
    log_message "Chromium wurde beendet und wird neu gestartet."
  fi

  sleep 2
done
