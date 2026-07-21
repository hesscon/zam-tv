# zam-tv

Minimale Signage-Software fuer einen Raspberry Pi 4 mit Flask, YAML-Konfiguration und Docker.

## Start mit Docker

```bash
docker compose up --build
```

Danach ist die App unter diesen URLs erreichbar:
- `http://localhost:8000/admin`
- `http://localhost:8000/screen`

Wenn du Quellcode geaendert hast, brauchst du aktuell einen Rebuild:

```bash
docker compose up --build
```

Der Grund: Im Compose-Setup werden nur `config/` und `data/uploads/` als Volumes gemountet, nicht der App-Code.

## Aktueller Stand

- Eine einzelne Flask-App fuer Admin und Screen
- Konfiguration komplett ueber `config/content.yaml`
- Admin-Seite mit YAML-Editor, Dateiliste, Upload-Funktion und Aufraeumen unbenutzter Medien
- Screen zeigt aktive Inhalte nacheinander an
- Nach einem kompletten Playlist-Durchlauf laedt sich `/screen` neu und uebernimmt so neue Konfigurationsaenderungen
- Videos laufen genau einmal komplett durch und wechseln dann automatisch weiter
- Unterstuetzte Inhaltstypen: `image`, `video`, `web`, `calendar`
- `calendar` erzeugt zur Laufzeit einzelne Event-Slides aus einer ICS-Quelle
- Die erzeugten `calendar`-Slides werden fuer 15 Minuten im Speicher gecacht, damit ICS-Fetch und Parsing nicht bei jedem Request erneut passieren

## Routen

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
```

Wichtige Felder:
- `items`: Liste aller Inhalte in Wiedergabereihenfolge
- `enabled`: Nur aktive Eintraege werden auf dem Screen gezeigt
- `content`: URL fuer `web` und `calendar`, Dateiname relativ zu `data/uploads/` fuer `image` und `video`
- `duration`: Pflicht fuer `image`, `web` und `calendar`
- `video` braucht keine `duration`, sondern laeuft einmal komplett durch
- `calendar` kann mit `categories` und `days_ahead` gefiltert werden
- Wenn ein spaeterer Kalender-Refresh fehlschlaegt, wird der letzte erfolgreiche Stand weiterverwendet

## Besonderheiten und Grenzen

- `web`-Eintraege werden aktuell per `iframe` angezeigt.
- Manche Webseiten verbieten das Einbetten per Sicherheits-Header. Dann erscheinen sie im Screen nicht sinnvoll oder gar nicht.
- Aenderungen aus `/admin` werden nicht sofort mitten in der laufenden Anzeige uebernommen, sondern spaetestens nach dem naechsten kompletten Playlist-Durchlauf.
- Die Admin-Oberflaeche hat aktuell bewusst keine Zugangsbeschraenkung.

## Wichtige Ordner

- `config/content.yaml`: Zentrale Playlist-Konfiguration
- `data/uploads/`: Bilder und Videos fuer lokale Medieninhalte
- `docs/calendar.md`: Entscheidungen und Plan fuer die ICS-/Kalender-Logik
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
