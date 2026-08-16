# Raspberry Pi Installation

## Ziel
Diese Anleitung beschreibt einen einfachen und robusten Betrieb von `zam-tv` auf einem Raspberry Pi 4 mit genau einem Bildschirm.

Die empfohlene Zielumgebung ist:
- Raspberry Pi 4
- Raspberry Pi OS (64-bit) mit Desktop
- Docker Engine + Docker Compose Plugin
- Chromium im Kiosk-Modus
- automatischer Start nach dem Boot

Warum Desktop und nicht Lite:
- Fuer den Kiosk-Modus brauchen wir einen grafischen Browser.
- Aktuelle Raspberry-Pi-OS-Versionen nutzen dafuer standardmaessig `labwc`.
- Mit Desktop + Auto-Login ist der Start von Chromium am einfachsten.

## Uebersicht
Der Startpfad auf dem Geraet ist:

1. Raspberry Pi bootet
2. Raspberry Pi OS meldet den Benutzer automatisch am Desktop an
3. Docker startet beim Boot
4. Der Container `zam-tv` startet automatisch
5. `labwc` startet ein kleines Skript
6. Das Skript wartet auf `http://127.0.0.1/screen`
7. Chromium startet im Vollbild und zeigt die Signage-Ansicht
8. Das Skript startet Chromium neu, wenn die Playlist zehn Minuten lang keinen
   Fortschritt meldet

## 1. OS vorbereiten

### Empfohlenes Image
Nutze im Raspberry Pi Imager:
- `Raspberry Pi OS (64-bit)`

Nicht empfohlen fuer dieses Projekt:
- `Lite`, weil dann ein eigener Grafik- und Browser-Startpfad noetig waere

### Imager-Einstellungen
Setze beim Flashen direkt diese Optionen:
- Hostname, zum Beispiel `zam-tv`
- Benutzername und Passwort
- WLAN, falls der Pi nicht per LAN angeschlossen wird
- SSH aktivieren
- Zeitzone `Europe/Berlin`

## 2. Erstes System-Setup
Nach dem ersten Boot lokal oder per SSH anmelden:

```bash
ssh <user>@zam-tv.local
```

Dann das System aktualisieren:

```bash
sudo apt update
sudo apt -y full-upgrade
sudo reboot
```

Nach dem Neustart diese Grundeinstellungen setzen:

```bash
sudo raspi-config
```

Empfohlene Punkte:
- `1 System Options` -> `S5 Boot / Auto Login` -> `B4 Desktop Autologin`
- `5 Localisation Options` -> Zeitzone pruefen
- optional Hostname pruefen

## 3. Docker installieren
Diese Schritte installieren Docker aus dem offiziellen Docker-Repository fuer Debian.

Alte Pakete entfernen, falls vorhanden:

```bash
for pkg in docker.io docker-doc docker-compose podman-docker containerd runc; do sudo apt-get remove -y $pkg; done
```

Paketquellen vorbereiten:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
```

Docker-Repository eintragen:

```bash
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
```

Docker installieren:

```bash
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

Installation pruefen:

```bash
sudo systemctl status docker --no-pager
sudo docker run hello-world
```

Optional den aktuellen Benutzer zur Docker-Gruppe hinzufuegen:

```bash
sudo usermod -aG docker $USER
newgrp docker
docker ps
```

Hinweis:
- Docker startet auf Debian-basierten Systemen in der Regel automatisch beim Boot.
- Das Projekt nutzt bereits `restart: unless-stopped` in `docker-compose.yml`.

## 4. Projekt auf den Pi kopieren
Empfohlener Zielpfad:

```bash
sudo mkdir -p /opt/zam-tv
sudo chown $USER:$USER /opt/zam-tv
```

Dann das Repo dorthin kopieren oder klonen, zum Beispiel:

```bash
git clone <REPO-URL> /opt/zam-tv
cd /opt/zam-tv
```

Falls das Projekt schon lokal vorliegt und per `scp` kopiert wird, danach ebenfalls:

```bash
cd /opt/zam-tv
```

## 5. Anwendung starten
Container bauen und im Hintergrund starten:

```bash
docker compose up -d --build
```

Pruefen, ob die App laeuft:

```bash
docker compose ps
curl -I http://127.0.0.1/
curl -I http://127.0.0.1/admin
curl -I http://127.0.0.1/screen
```

Wichtige URLs:
- `http://<pi-ip>/` (Admin-Seite; Weiterleitung auf `/admin`)
- `http://<pi-ip>/admin`
- `http://<pi-ip>/screen`
- lokal auf dem Pi: `http://127.0.0.1/screen`

Hinweis zu den Ports:
- `docker-compose.yml` veroeffentlicht die App auf Port `80` des Raspberry Pi.
- Im Container selbst laeuft Flask weiterhin auf Port `8000`.
- Deshalb wird Port `8000` in den von aussen oder vom Pi selbst aufgerufenen URLs nicht angegeben.

## 6. Kiosk-Pakete installieren
Fuer den Browser-Start und kleine Hilfswerkzeuge:

```bash
sudo apt install -y --no-install-recommends curl swayidle wtype wlr-randr
sudo apt install -y --no-install-recommends chromium
```

Falls das Paket `chromium` auf dem verwendeten Image nicht gefunden wird, versuche:

```bash
sudo apt install -y --no-install-recommends chromium-browser
```

Damit Chromium im Kiosk-Betrieb keine Uebersetzungs-Sprechblase einblendet, wird die
Uebersetzungsfunktion ueber eine verwaltete Browser-Richtlinie abgeschaltet:

```bash
sudo install -d -m 755 /etc/chromium/policies/managed
sudo tee /etc/chromium/policies/managed/zam-tv.json > /dev/null <<'EOF'
{
  "TranslateEnabled": false
}
EOF
```

Die Richtlinie ist zuverlaessiger als der veraltete Chromium-Schalter
`--disable-translate` und gilt ab dem naechsten Browser-Start.

## 7. Kiosk-Startskript anlegen
Wir starten Chromium nicht direkt aus `labwc`, sondern ueber ein kleines Skript.
Das Skript wartet zunaechst auf die lokale Web-App. Dadurch landet der Browser nach
einem Boot nicht auf einer Fehlerseite, waehrend Docker noch startet. Danach bleibt
es als einfacher Watchdog aktiv.

Das mitgelieferte Skript installieren:

```bash
mkdir -p ~/.local/bin
install -m 755 /opt/zam-tv/scripts/start-zam-tv-kiosk.sh ~/.local/bin/
```

Die Bildschirmseite sendet beim ersten Anzeigen und nach jedem Slide-Wechsel ein
Lebenszeichen. Bleibt dieses Lebenszeichen zehn Minuten aus, beendet das Skript nur
seine eigene Chromium-Instanz und startet sie neu. Ein beendeter Browser wird sofort
neu gestartet. Wenn stattdessen die Flask-App nicht erreichbar ist, wartet das
Skript auf Docker und startet den Browser nicht unnoetig wiederholt.

Warum `--password-store=basic`:
- Im Kiosk-Betrieb auf Raspberry Pi OS taucht sonst je nach Desktop-Umgebung eine stoerende Passwort- oder Schluesselbund-Abfrage von Chromium auf.
- Fuer diesen einfachen Einzelgeraet-Einsatz ist `basic` die pragmatische Variante, damit der Browser ohne Rueckfrage startet.

Warum die Wayland- und Sprachoptionen:
- `--ozone-platform=wayland` sorgt dafuer, dass Chromium auch bei einem manuellen Start per SSH die laufende Wayland-Sitzung verwendet.
- `--lang=de-DE` stellt die Sprache der Browser-Oberflaeche auf Deutsch.
- Die in Schritt 6 angelegte Richtlinie verhindert die Uebersetzungs-Einblendung.

## 8. Autostart fuer den Desktop setzen
Unter aktuellen Raspberry-Pi-OS-Versionen wird Desktop-Autostart ueber `labwc` konfiguriert.

### Mauszeiger automatisch ausblenden

Raspberry Pi OS verwendet mit `labwc` standardmaessig Wayland. Das fuer X11 gedachte Werkzeug `unclutter` funktioniert dort nicht. Stattdessen nutzen wir die in `labwc` eingebaute Aktion `HideCursor`. Dabei wird kein unsichtbares Cursor-Bild verwendet: `labwc` blendet den Mauszeiger aus und zeigt ihn bei der naechsten Mausbewegung wieder an.

Zuerst die installierte Version pruefen:

```bash
labwc --version
```

Die Version muss mindestens `0.8.4` sein. Falls eine aeltere Version angezeigt wird, zuerst Raspberry Pi OS aktualisieren wie in Abschnitt 2 beschrieben.

Die systemweite `labwc`-Konfiguration einmalig als Benutzerkonfiguration uebernehmen. Eine bereits vorhandene Datei wird durch `cp -n` nicht ueberschrieben:

```bash
mkdir -p ~/.config/labwc
cp -n /etc/xdg/labwc/rc.xml ~/.config/labwc/rc.xml
nano ~/.config/labwc/rc.xml
```

Im vorhandenen `<keyboard>`-Abschnitt, am besten direkt nach `<default />`, diese Tastenzuordnung ergaenzen:

```xml
<keybind key="A-W-h">
  <action name="HideCursor" />
</keybind>
```

Wenn du in einem Terminal direkt auf dem Desktop arbeitest, kannst du die geaenderte Konfiguration sofort neu einlesen:

```bash
labwc --reconfigure
```

Zum direkten Testen:

```bash
wtype -M alt -M logo h -m alt -m logo
```

Der Mauszeiger sollte sofort verschwinden und bei der naechsten Mausbewegung wieder erscheinen.
Bei einer reinen SSH-Installation koennen diese beiden direkten Tests entfallen. Die Konfiguration wird spaetestens beim Neustart in Abschnitt 9 geladen.

### Autostart-Datei anlegen

Datei anlegen:

```bash
mkdir -p ~/.config/labwc
nano ~/.config/labwc/autostart
```

Empfohlener Inhalt:

```bash
# Bildschirm nicht abdunkeln oder sperren.
wlr-randr --output HDMI-A-1 --on || true

# Mauszeiger nach zwei Sekunden ohne Eingabe ausblenden.
swayidle -w timeout 2 'wtype -M alt -M logo h -m alt -m logo' &

# Kiosk-Browser im Hintergrund starten.
$HOME/.local/bin/start-zam-tv-kiosk.sh &
```

Hinweis:
- Die konkrete Display-Bezeichnung kann je nach Setup abweichen.
- Wenn `wlr-randr` nicht noetig ist, kann die erste Zeile auch entfallen.

## 9. Bildschirm-Blanking deaktivieren
Bei Signage soll der Bildschirm dauerhaft an bleiben.

Oeffne:

```bash
sudo nano /boot/firmware/cmdline.txt
```

Ergaenze in der bestehenden einzelnen Zeile am Ende:

```text
 consoleblank=0
```

Dann neu starten:

```bash
sudo reboot
```

Optional kann zusaetzlich im Desktop die automatische Bildschirmabschaltung deaktiviert werden, falls aktiv.

## 10. Funktion testen
Nach dem Neustart sollte automatisch Chromium im Vollbild erscheinen.

Pruefe bei Problemen in dieser Reihenfolge:

### Docker-Status

```bash
docker compose -f /opt/zam-tv/docker-compose.yml ps
docker compose -f /opt/zam-tv/docker-compose.yml logs --tail=100
```

### App lokal erreichbar

```bash
curl -I http://127.0.0.1/screen
curl -I http://127.0.0.1/admin
```

Wenn Chromium laeuft und bereits einen Slide angezeigt hat, antwortet auch der
Watchdog-Endpunkt erfolgreich:

```bash
curl -I http://127.0.0.1/screen/health
```

Ohne vorheriges Lebenszeichen oder nach mehr als zehn Minuten Stillstand ist der
Status erwartungsgemaess `503 Service Unavailable`.

### Kiosk-Log

```bash
tail -n 100 ~/.local/state/zam-tv-kiosk.log
```

### Labwc-Autostart pruefen

```bash
cat ~/.config/labwc/autostart
```

### Kiosk-Prozesse pruefen

```bash
pgrep -af 'chromium.*--kiosk'
pgrep -af '^swayidle '
```

### Chromium-Watchdog gezielt testen

Ein beendeter Browser muss nach wenigen Sekunden mit einer neuen PID erscheinen:

```bash
pgrep -af 'chromium.*--kiosk.*zam-tv-chromium-profile'
kill <CHROMIUM-PID>
sleep 5
pgrep -af 'chromium.*--kiosk.*zam-tv-chromium-profile'
tail -n 20 ~/.local/state/zam-tv-kiosk.log
```

Den Haengefall kann man realistisch mit `SIGSTOP` simulieren. Dabei bleiben die
Prozesse vorhanden, koennen aber keine Slides wechseln und keine Lebenszeichen
mehr senden:

```bash
pkill -STOP -f -- "--user-data-dir=$HOME/.local/state/zam-tv-chromium-profile"
```

Nach etwas mehr als zehn Minuten muss das Log den fehlenden Bildschirmfortschritt
und den automatischen Neustart melden. Danach sollen `/screen` und `/screen/health`
wieder erfolgreich antworten:

```bash
tail -n 20 ~/.local/state/zam-tv-kiosk.log
curl -I http://127.0.0.1/screen
curl -I http://127.0.0.1/screen/health
pgrep -af 'chromium.*--kiosk.*zam-tv-chromium-profile'
```

Falls der Test vorzeitig abgebrochen werden muss, lassen sich die angehaltenen
Prozesse wieder fortsetzen:

```bash
pkill -CONT -f -- "--user-data-dir=$HOME/.local/state/zam-tv-chromium-profile"
```

### Bildschirm-Blanking pruefen

```bash
grep -o 'consoleblank=[^ ]*' /proc/cmdline
```

Die Ausgabe sollte `consoleblank=0` enthalten.

### Mauszeiger bleibt sichtbar

Pruefe zuerst Version und Hilfsprogramme:

```bash
labwc --version
command -v swayidle
command -v wtype
```

`labwc` muss mindestens Version `0.8.4` haben. Teste danach die eingerichtete Tastenzuordnung direkt:

```bash
wtype -M alt -M logo h -m alt -m logo
```

Wenn der Mauszeiger dadurch verschwindet, liegt der Fehler wahrscheinlich in der Autostart-Datei. Pruefe dort insbesondere das `&` am Ende der `swayidle`-Zeile.

## 11. Alltag und Betrieb

### Konfiguration bearbeiten
Im Netzwerk:

- `http://<pi-ip>/`

### Medien hochladen
Die App speichert Uploads in:

- `/opt/zam-tv/data/uploads/`

Der letzte erfolgreiche Kalender-Snapshot liegt in:

- `/opt/zam-tv/data/cache/calendar_cache.json`

### Nach Updates neu bauen
Wenn du den Code aktualisiert hast:

```bash
cd /opt/zam-tv
docker compose up -d --build
```

Wenn sich auch das Kiosk-Skript geaendert hat, erneut auf den Host kopieren und den
Pi einmal neu starten:

```bash
install -m 755 /opt/zam-tv/scripts/start-zam-tv-kiosk.sh ~/.local/bin/
sudo reboot
```

### Komplett neu starten

```bash
sudo reboot
```

## 12. Sinnvolle spaetere Verbesserungen
Nicht noetig fuer V1, aber praktisch im Dauerbetrieb:

- SSH-Login nur noch per Key
- `/admin` im lokalen Netz per Reverse Proxy oder Firewall einschraenken
- Betrieb auf SSD statt nur auf microSD

## Troubleshooting

### Chromium startet nicht
Pruefe den Programmnamen:

```bash
which chromium
which chromium-browser
```

Mindestens einer der beiden Befehle sollte einen Programmpfad ausgeben. Falls beide Ausgaben leer bleiben, installiere Chromium wie in Abschnitt 6 beschrieben.

### Chromium zeigt eine Passwort- oder Keyring-Abfrage
Pruefe, ob das Startskript diese Option enthaelt:

```bash
--password-store=basic
```

Ohne diese Option kann Chromium auf Raspberry Pi OS im Kiosk-Betrieb versuchen, einen nativen Passwortspeicher zu verwenden und dabei eine blockierende Rueckfrage anzeigen.

### Browser startet, zeigt aber nichts an
Pruefe zuerst:

```bash
curl -I http://127.0.0.1/screen
docker compose logs --tail=100
```

### Chromium zeigt eine Uebersetzungs-Einblendung
Pruefe, ob die verwaltete Chromium-Richtlinie vorhanden ist:

```bash
cat /etc/chromium/policies/managed/zam-tv.json
```

Sie muss `"TranslateEnabled": false` enthalten. Starte Chromium anschliessend neu
oder starte den Raspberry Pi mit `sudo reboot` neu.

### Externe Webseiten bleiben leer
Das ist bei `web`-Eintraegen moeglich, wenn die Zielseite das Einbetten per `iframe` verbietet.
Das ist eine in `README.md` bereits beschriebene Einschraenkung des aktuellen Projekts.

### Kalenderdaten laden nicht
Pruefe Netzwerk, Ziel-URL und die Logs des Containers:

```bash
docker compose logs --tail=100
```

## Quellen
- Raspberry Pi Kiosk Tutorial: https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/
- Docker Engine auf Debian: https://docs.docker.com/engine/install/debian/
- labwc-Aktion `HideCursor`: https://labwc.github.io/labwc-actions.5.html
- labwc 0.8.4 Release Notes: https://github.com/labwc/labwc/releases/tag/0.8.4
