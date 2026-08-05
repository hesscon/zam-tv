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
- Admin-Seite mit YAML-Editor, Dateiliste, Upload-Funktion und Aufraeumen unbenutzter Medien
- Screen zeigt aktive Inhalte nacheinander an
- Nach einem kompletten Playlist-Durchlauf laedt sich `/screen` neu und uebernimmt so neue Konfigurationsaenderungen
- Videos laufen genau einmal komplett durch und wechseln dann automatisch weiter
- Unterstuetzte Inhaltstypen: `image`, `video`, `web`, `calendar`
- `calendar` erzeugt im Hintergrund einzelne Event-Slides aus einer ICS-Quelle
- Kalender-Slides zeigen bei vorhandener Event-URL einen QR-Code zur Veranstaltungsseite
- Ein Hintergrund-Thread aktualisiert den Kalender-Snapshot sofort nach dem Start und danach alle 15 Minuten
- Der letzte erfolgreiche Kalender-Snapshot wird in `data/cache/calendar_cache.json` gespeichert und beim Neustart sofort geladen
- Neue oder in Titel beziehungsweise Beschreibung geaenderte Events werden gesammelt an den lokalen Caption-Worker uebergeben; jedes fertige JSONL-Ergebnis wird sofort im Snapshot persistiert, unveraenderte Captions kommen aus dem vorherigen Snapshot
- Der Caption-Worker laeuft standardmaessig mit Nice-Level 10, damit Flask und die lokale Bildschirmanzeige bei CPU-Konkurrenz Vorrang haben
- `/screen` liest nur den fertigen Snapshot und wartet weder auf ICS-Abruf noch auf Parsing

## Routen

- `/`: Weiterleitung zur Admin-Seite unter `/admin`
- `/admin`: YAML-Konfiguration ansehen und bearbeiten
- `/admin/cleanup-unused`: Nicht referenzierte Upload-Dateien loeschen
- `/admin/upload`: Medien nach `data/uploads/` hochladen
- `/admin/save`: Formularziel zum Speichern der YAML
- `/screen`: Signage-Ansicht fuer den Bildschirm
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
