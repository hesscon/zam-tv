# LLM-Caption-Worker testen

Der Worker liest ein JSON-Array aus `stdin`, laedt das Modell einmal und
schreibt die Ergebnisse als JSON nach `stdout`. Der erste Modellaufruf wird
per JSON-Schema auf die Enum-Felder `activity` und `term` beschraenkt. Der
Worker berechnet daraus, ob eine Caption erforderlich ist. Nur
Kombinationen mit einer addierten Schwere von mindestens zwei erzeugen eine
Caption. `explicit` und `common` zaehlen null, `context_specific` eins,
`generic`, `missing` und `unfamiliar` zwei. Bei Bedarf erzeugt ein zweiter
Aufruf `{"caption":"..."}`. Der Worker gibt nach aussen weiterhin nur `uid`
und `caption` aus. Laufzeiten und Fehler erscheinen auf `stderr`.

## Ziel der Caption

Titel und Caption sollen gemeinsam einer Person ohne besonderes Vorwissen
verstaendlich machen, was bei der Veranstaltung passiert. Die Caption ist
optional und soll nur die kleinste wichtige Erklaerung ergaenzen, die im Titel
fehlt.

Ein eigener Modellaufruf prueft deshalb ausschliesslich den Titel. Die
Beschreibung wird diesem Aufruf nicht uebergeben. Das Modell bewertet:

- `activity`: `explicit`, `generic` oder `missing`
- `term`: `common`, `context_specific` oder `unfamiliar`

`explicit` und `common` zaehlen null Punkte, `context_specific` einen Punkt
und `generic`, `missing` sowie `unfamiliar` zwei Punkte. Ab zwei Punkten folgt
der zweite Modellaufruf mit Titel und Beschreibung.

Der Generator erzeugt nur dann Text, wenn die Beschreibung eine hilfreiche
Information zu Aktivitaet, Ziel, Ergebnis oder einem unklaren Begriff
enthaelt. Wiederholt sie im Wesentlichen nur den Titel oder enthaelt nur
organisatorische Angaben, ist `{"caption":""}` ein erfolgreiches Ergebnis.

Eine Caption ist insbesondere sinnvoll bei:

- Eigennamen und Wortspielen wie `ZAMraeumen`
- Abkuerzungen wie `DI.Day`
- moeglicherweise unbekannten Begriffen wie `Cajon`
- Titeln ohne erkennbare Aktivitaet wie `Katzentag`
- englischen Fachbegriffen, die fuer das allgemeine Publikum unklar sein
  koennen

Fuer die Formulierung gelten diese Leitlinien:

- Die konkrete Aktivitaet oder das Thema soll klar werden.
- Ungelaeufige Begriffe sollen in einfachem Deutsch umschrieben werden.
- Die Caption soll etwa drei bis acht Woerter enthalten.
- Es duerfen nur Informationen aus Titel und Beschreibung verwendet werden.
- Der knappe Platz ist fuer die inhaltliche Erklaerung gedacht, nicht fuer
  Personen, Ort, Termin, Anmeldung oder Werbung.
- Eine blosse Wiederholung oder Umstellung des Titels ist keine sinnvolle
  Caption.
- Ein leerer String ist ein erwuenschtes Ergebnis, wenn der Titel bereits
  ausreicht oder die Beschreibung keine hilfreiche inhaltliche Ergaenzung
  ermoeglicht.

Beispiele:

| Titel | Caption |
| --- | --- |
| Medizinischer Hilfsdienst – Arztbriefe erklaert | *(leer)* |
| Aktzeichnen | *(leer)* |
| Holzwerkstatt Orgatreffen | *(leer)* |
| Katzentag | Katzen mit verschiedenen Techniken gestalten |
| Cajon Bau | Ein Schlaginstrument aus Holz bauen |
| ZAMraeumen | Werkstaetten gemeinsam aufraeumen und vorbereiten |
| DI.Day | Wege zu mehr digitaler Unabhaengigkeit |
| Open Source Contributor Meetup | Gemeinsam an freier Software arbeiten |

Jedes Event mit Beschreibung erhaelt einen kurzen Klassifikationsaufruf. Nur
wenn eine Caption erforderlich ist, folgt der Aufruf zur Texterzeugung. Beide
Aufgaben haben getrennte System-Prompts, Beispiele und JSON-Schemas. Das Modell
wird trotzdem nur einmal pro Worker-Durchlauf geladen. Der zweite Aufruf darf
sich mit einer leeren Caption enthalten; dies gilt als erfolgreicher Abschluss
und nicht als Modellfehler.

Die Prompt-Beispiele sind kuenstliche Veranstaltungen und ueberschneiden sich
nicht mit den Titeln der Test-Fixture. Die erwarteten Klassifikationen der 20
Regressionsevents stehen getrennt in
`tests/fixtures/event-caption-expected-classifications.json`. Tests stellen
die Trennung und Konsistenz sicher, damit die Auswertung nicht durch
wiederholte Beispielantworten verfaelscht wird. Da ihre Fehlermuster bereits
zur Promptentwicklung verwendet wurden, sind diese Events kein unabhaengiger
Holdout-Test mehr.

## Vorbereitung

Aktuelles Testmodell:

```text
data/models/gemma-4-E4B-it-Q5_K_M.gguf
```

Die Modelldatei wird nicht in Git eingecheckt. Fuer die lokale Ausfuehrung
wird eine eigene Python-Umgebung empfohlen:

```bash
python3 -m venv .venv-llm
.venv-llm/bin/pip install -r requirements-llm.txt
```

Andere lokale GGUF-Modelle koennen weiterhin ueber `--model` verglichen
werden. Gemma ist derzeit nur das bevorzugte Testmodell, noch keine
abschliessende Raspberry-Pi-Empfehlung.

## Eingabe

```json
[
  {
    "uid": "event-123",
    "title": "Pecha-Kucha-Nacht",
    "description": "Mehrere Vortragende praesentieren unterschiedliche Themen in kurzen Vortraegen."
  }
]
```

Die Eingabe beispielsweise als `events.json` speichern und den Worker im Container starten:

```bash
docker compose run --rm -T zam-tv \
  python -m app.services.event_caption_worker \
  --model data/models/gemma-4-E4B-it-Q5_K_M.gguf \
  < events.json \
  > captions.json
```

Standardmaessig verwendet der Worker zwei CPU-Threads und eine niedrige Temperatur von `0.2`. Fuer Vergleiche auf dem Raspberry Pi koennen beispielsweise `--threads 1`, `--threads 4` oder `--temperature 0.7` gesetzt werden.

Alternativ kann der Worker direkt in der lokalen LLM-Umgebung ausgefuehrt
werden:

```bash
.venv-llm/bin/python app/services/event_caption_worker.py \
  --model data/models/gemma-4-E4B-it-Q5_K_M.gguf \
  < events.json \
  > captions.json
```

Nur die Titelklassifikation laesst sich mit `--classify-only` ausfuehren:

```bash
.venv-llm/bin/python app/services/event_caption_worker.py \
  --model data/models/gemma-4-E4B-it-Q5_K_M.gguf \
  --classify-only \
  < tests/fixtures/event-caption-events.json
```

Dieser Modus gibt `activity`, `term` und das daraus berechnete
`needs_caption` aus. Er startet keine Caption-Erzeugung. `activity` verwendet
die Werte `explicit`, `generic` und `missing`; `term` verwendet `common`,
`context_specific` und `unfamiliar`.

## Ausgabe

```json
[
  {
    "uid": "event-123",
    "caption": "Kurze Vortraege zu vielfaeltigen Themen"
  }
]
```

Eine leere Caption ohne `error` ist eine erfolgreiche Enthaltung. Ein Fehler
bei einem einzelnen Event erzeugt eine leere Caption mit `error`, ohne die
restlichen Events abzubrechen. Ein unlesbares Eingabe-JSON oder ein fehlendes
Modell beendet den Worker mit Exit-Code `1`.
