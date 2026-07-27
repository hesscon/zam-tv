# Calendar / ICS

## Ziel
Der Screen im Schaufenster soll automatisch kommende Veranstaltungen aus einer ICS-Datei als eigene Slides anzeigen.

Der Anwendungsfall ist:
- Das ZAM veranstaltet Termine im Haupthaus
- Relevante Veranstaltungen sollen automatisch auf dem Monitor erscheinen
- Die YAML-Konfiguration soll dabei einfach bleiben

## Geplante YAML-Struktur

Ein Kalender-Eintrag in der Playlist ist kein einzelner fertiger Slide, sondern eine Quelle fuer automatisch erzeugte Slides.

Beispiel:

```yaml
- type: calendar
  content: https://example.com/events.ics
  duration: 12
  enabled: true
  categories:
    - Veranstaltung
  days_ahead: 14
  fix_mec_timezone: false
```

Bedeutung:
- `content`: URL der ICS-Datei
- `duration`: Anzeigedauer pro erzeugtem Event-Slide
- `enabled`: Aktiv/Inaktiv
- `categories`: Nur Events mit mindestens einer passenden Kategorie werden uebernommen
- `days_ahead`: Zeitfenster ab jetzt, in dem Events beruecksichtigt werden
- `fix_mec_timezone`: Optionaler Workaround fuer fehlerhafte ICS-Exporte des WordPress-Plugins Modern Events Calendar (Standard: `false`)

## MEC-Zeitzonen-Workaround

Einige MEC-Exporte addieren den Berliner UTC-Abstand irrtuemlich auf die
gewuenschte Ortszeit und kennzeichnen das Ergebnis trotzdem mit
`TZID=Europe/Berlin`. Dadurch liegt ein im Winter angelegter Termin eine Stunde
und ein im Sommer angelegter Termin zwei Stunden zu spaet.

Fuer eine betroffene MEC-Quelle wird die Korrektur direkt am Kalender-Eintrag
aktiviert:

```yaml
- type: calendar
  content: https://www.zam.haus/?mec-ical-feed=1
  duration: 12
  enabled: true
  categories:
    - Veranstaltung
  days_ahead: 30
  fix_mec_timezone: true
```

Die Korrektur wird auf `DTSTART`, `DTEND` sowie lokale `RDATE`- und
`EXDATE`-Werte mit `TZID=Europe/Berlin` angewendet, bevor Wiederholungen
expandiert werden. UTC-Werte mit einem abschliessenden `Z` bleiben
unveraendert. Korrekte ICS-Quellen duerfen den Schalter nicht aktivieren.

## Verwendete ICS-Felder

Fuer V1 sollen nur diese Felder ausgewertet werden:
- `CATEGORIES`
- `ATTACH`
- `SUMMARY`
- `DTSTART`
- `RDATE`, `RRULE` und `EXDATE` fuer Wiederholungen
- `URL`

Bewusst nicht Teil von V1:
- `DESCRIPTION`
- komplexe Detaildarstellungen

## Filterregeln

Fuer die erste Version gelten diese Regeln:
- Nur Events im konfigurierten Zeitfenster, z. B. naechste 14 Tage
- Nur Events, deren `CATEGORIES` mindestens einen passenden Eintrag enthalten
- Beispiel: `Veranstaltung`

## Generierung von Slides

Ein YAML-Eintrag vom Typ `calendar` erzeugt zur Laufzeit mehrere interne Playlist-Eintraege.

Beispiel:
- In YAML steht ein einzelner `calendar`-Eintrag
- In der ICS-Datei werden 3 passende Events gefunden
- Daraus entstehen 3 Event-Slides in der Playlist

Wichtig:
- Die erzeugten Slides erscheinen genau an der Stelle in der Playlist, an der der `calendar`-Eintrag steht
- Die `duration` des YAML-Eintrags gilt fuer jedes erzeugte Event einzeln
- Bei 3 gefundenen Events mit `duration: 12` laufen also 3 Slides mit jeweils 12 Sekunden

## Darstellung eines Event-Slides

Ein erzeugter Kalender-Slide zeigt:
- Bild aus `ATTACH`, wenn vorhanden
- Kategorie
- Titel aus `SUMMARY`
- Datum/Uhrzeit aus `DTSTART`
- QR-Code zur Veranstaltungsseite aus `URL`, wenn vorhanden

Wenn kein `ATTACH` vorhanden ist:
- Das Event wird trotzdem angezeigt
- Der Slide wird dann einfach ohne Bild dargestellt

## Beobachtungen zur echten ZAM-ICS-Datei

Aus der bereitgestellten Datei ergeben sich diese praktischen Punkte:
- `CATEGORIES` ist vorhanden und fuer Filter gut nutzbar
- `ATTACH` ist meist eine direkte Bild-URL
- `URL` verweist direkt auf die zugehoerige Veranstaltungsseite
- `DTSTART` kommt mit `TZID=Europe/Berlin`
- `DESCRIPTION` ist oft leer oder sehr lang und teils unruhig formatiert
- Wiederholungen werden mit `RDATE`, `RRULE` und `EXDATE` beschrieben

## Vereinfachungen fuer V1

Um die Implementierung schlank zu halten:
- `DESCRIPTION` wird komplett ignoriert
- fehlendes `ATTACH` blendet nur das Bild aus, nicht das Event
- Wiederholungen werden nur innerhalb des konfigurierten Zeitfensters expandiert

## Offene spaetere Erweiterungen

Moegliche spaetere Ausbaustufen:
- sortier- oder priorisierbare Event-Slides
- weitere Filter, z. B. nach Ort
- optionale Beschreibung oder Kurztext
- eigenes Layout fuer mehrere gleichzeitig sichtbare Events
