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
- Admin-Seite mit einem grossen YAML-Textfeld
- Screen zeigt aktive Inhalte nacheinander an
- Nach einem kompletten Playlist-Durchlauf laedt sich `/screen` neu und uebernimmt so neue Konfigurationsaenderungen
- Unterstuetzte Inhaltstypen: `image`, `video`, `web`, `calendar`

## Routen

- `/admin`: YAML-Konfiguration ansehen und bearbeiten
- `/admin/save`: Formularziel zum Speichern der YAML
- `/screen`: Signage-Ansicht fuer den Bildschirm
- `/uploads/<filename>`: Lokale Medien aus `data/uploads/`

## YAML-Struktur

Ein minimales Beispiel:

```yaml
orientation: portrait
rotation_seconds: 10
items:
  - type: web
    title: ZAM
    url: https://zam.haus
    duration: 10
    enabled: true

  - type: image
    title: Beispielbild
    path: bild.jpg
    duration: 8
    enabled: true
```

Wichtige Felder:
- `orientation`: `portrait` oder `landscape`
- `rotation_seconds`: Fallback-Dauer, wenn ein Eintrag keine eigene `duration` hat
- `items`: Liste aller Inhalte in Wiedergabereihenfolge
- `enabled`: Nur aktive Eintraege werden auf dem Screen gezeigt
- `path`: Dateiname relativ zu `data/uploads/`
- `url`: Zieladresse fuer Web-Inhalte

## Besonderheiten und Grenzen

- `web`-Eintraege werden aktuell per `iframe` angezeigt.
- Manche Webseiten verbieten das Einbetten per Sicherheits-Header. Dann erscheinen sie im Screen nicht sinnvoll oder gar nicht.
- Aenderungen aus `/admin` werden nicht sofort mitten in der laufenden Anzeige uebernommen, sondern spaetestens nach dem naechsten kompletten Playlist-Durchlauf.
- Die Admin-Oberflaeche hat aktuell bewusst keine Zugangsbeschraenkung.

## Wichtige Ordner

- `config/content.yaml`: Zentrale Playlist-Konfiguration
- `data/uploads/`: Bilder und Videos fuer lokale Medieninhalte
- `app/templates/`: HTML-Templates fuer Admin und Screen
- `app/static/`: CSS und JavaScript fuer die Anzeige

## Entwicklung ohne Docker

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
