# zam-tv

Minimale Signage-Software fuer einen Raspberry Pi 4 mit Flask, YAML-Konfiguration und Docker.

## Start mit Docker

```bash
docker compose up --build
```

Danach ist die App unter diesen URLs erreichbar:
- `http://localhost/` (Admin-Seite; Weiterleitung auf `/admin`)
- `http://localhost/screen`

Wenn du Quellcode geaendert hast, brauchst du aktuell einen Rebuild:

```bash
docker compose up --build
```

Der Grund: Im Compose-Setup werden nur Konfiguration und persistente Daten als
Volumes gemountet, nicht der App-Code.

## Aktueller Stand

- Eine einzelne Flask-App fuer Admin und Screen
- Konfiguration komplett ueber `config/content.yaml`
- Admin-Seite mit YAML-Editor, Dateiliste, Upload-Funktion, Aufraeumen unbenutzter
  Medien und den letzten 100 Anwendungsmeldungen des laufenden Prozesses
- Screen zeigt aktive Inhalte nacheinander an
- Nach einem kompletten Playlist-Durchlauf laedt sich `/screen` neu und uebernimmt so neue Konfigurationsaenderungen
- `/screen` meldet beim ersten Anzeigen und nach jedem Slide-Wechsel seinen Fortschritt; das Kiosk-Skript startet Chromium nach zehn Minuten Stillstand neu
- Videos laufen genau einmal komplett durch und wechseln dann automatisch weiter
- Unterstuetzte Inhaltstypen: `image`, `video`, `web`, `calendar`
- `calendar` erzeugt im Hintergrund einzelne Event-Slides aus einer ICS-Quelle
- Kalender-Slides zeigen bei vorhandener Event-URL einen QR-Code zur Veranstaltungsseite
- Ein Hintergrund-Thread aktualisiert den Kalender-Snapshot sofort nach dem Start und danach alle 15 Minuten
- Der letzte erfolgreiche Kalender-Snapshot wird in `data/cache/calendar_cache.json` gespeichert und beim Neustart sofort geladen
- Wenn `caption_generation_enabled: true` gesetzt ist, werden neue oder in Titel beziehungsweise Beschreibung geaenderte Events gesammelt an den lokalen Caption-Worker uebergeben; jedes fertige JSONL-Ergebnis wird sofort im Snapshot persistiert, unveraenderte Captions kommen aus dem vorherigen Snapshot
- Der Caption-Worker laeuft standardmaessig mit Nice-Level 10, damit Flask und die lokale Bildschirmanzeige bei CPU-Konkurrenz Vorrang haben
- `/screen` liest nur den fertigen Snapshot und wartet weder auf ICS-Abruf noch auf Parsing

## Routen

- `/`: Weiterleitung zur Admin-Seite unter `/admin`
- `/admin`: YAML-Konfiguration ansehen und bearbeiten
- `/admin/cleanup-unused`: Nicht referenzierte Upload-Dateien loeschen
- `/admin/upload`: Medien nach `data/uploads/` hochladen
- `/admin/save`: Formularziel zum Speichern der YAML
- `/screen`: Signage-Ansicht fuer den Bildschirm
- `/screen/heartbeat`: Lebenszeichen der Signage-Ansicht
- `/screen/health`: Watchdog-Status des letzten Lebenszeichens
- `/uploads/<filename>`: Lokale Medien aus `data/uploads/`

## YAML-Struktur

Ein minimales Beispiel:

```yaml
items:
  - type: web
    content: https://zam.haus
    duration: 10
    enabled: true

  - type: image
    content: bild.jpg
    duration: 8
    enabled: true

  - type: video
    content: clip.mp4
    enabled: true

  - type: calendar
    content: https://example.com/events.ics
    duration: 12
    enabled: true
    # Ressourcenschonend standardmaessig ausgeschaltet
    caption_generation_enabled: false
    categories:
      - Veranstaltung
    days_ahead: 14
    fix_mec_timezone: false
```

Wichtige Felder:
- `items`: Liste aller Inhalte in Wiedergabereihenfolge
- `enabled`: Nur aktive Eintraege werden auf dem Screen gezeigt
- `content`: URL fuer `web` und `calendar`, Dateiname relativ zu `data/uploads/` fuer `image` und `video`
- `duration`: Pflicht fuer `image`, `web` und `calendar`
- `video` braucht keine `duration`, sondern laeuft einmal komplett durch
- `calendar` kann mit `categories` und `days_ahead` gefiltert werden
- Bei wiederkehrenden Kalender-Events wird nur der unmittelbar naechste Termin angezeigt
- `caption_generation_enabled: true` aktiviert KI-generierte Kurztexte fuer den jeweiligen Kalender; ohne das Feld ist die Funktion ausgeschaltet
- `fix_mec_timezone: true` aktiviert bei fehlerhaften Modern Events Calendar-Feeds die Korrektur der doppelt aufgeschlagenen Berliner UTC-Abweichung
- Waehrend eines Kalender-Refreshs und bei Fehlern wird der letzte erfolgreiche Stand weiterverwendet
- Beim allerersten Start ohne Cache-Datei bleibt der Kalenderbereich leer, bis der erste Hintergrund-Refresh erfolgreich abgeschlossen ist

## Besonderheiten und Grenzen

- `web`-Eintraege werden aktuell per `iframe` angezeigt.
- Manche Webseiten verbieten das Einbetten per Sicherheits-Header. Dann erscheinen sie im Screen nicht sinnvoll oder gar nicht.
- Aenderungen aus `/admin` werden nicht sofort mitten in der laufenden Anzeige uebernommen, sondern spaetestens nach dem naechsten kompletten Playlist-Durchlauf.
- Die Admin-Oberflaeche hat aktuell bewusst keine Zugangsbeschraenkung.

## Wichtige Ordner

- `config/content.yaml`: Zentrale Playlist-Konfiguration
- `data/cache/calendar_cache.json`: Letzter erfolgreicher Kalender-Snapshot
- `data/uploads/`: Bilder und Videos fuer lokale Medieninhalte
- `docs/calendar.md`: Entscheidungen und Plan fuer die ICS-/Kalender-Logik
- `docs/llm-caption-worker.md`: Lokaler Test fuer automatisch erzeugte Event-Kurztexte
- `docs/llm-caption-validator.md`: Unabhaengige LLM-Pruefung erzeugter Event-Kurztexte
- `docs/raspberry-pi-installation.md`: Konkrete Installationsanleitung fuer Raspberry Pi, Docker und Kiosk-Modus
- `app/templates/`: HTML-Templates fuer Admin und Screen
- `app/static/`: CSS und JavaScript fuer die Anzeige

## Entwicklung ohne Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
