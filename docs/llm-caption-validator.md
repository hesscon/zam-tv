# LLM-Caption-Validator testen

Der Validator ist ein eigener Prozess und unabhaengig vom Caption-Generator. Er
liest ein JSON-Array aus `stdin`, laedt ein frei waehlbares GGUF-Modell einmal
und schreibt die Pruefergebnisse als JSON nach `stdout`. Logs erscheinen auf
`stderr`.

## Eingabe

```json
[
  {
    "uid": "event-123",
    "title": "Repair-Café",
    "description": "Gemeinsam werden defekte Alltagsgegenstände repariert.",
    "caption": "Gemeinsam defekte Geräte reparieren"
  }
]
```

## Aufruf

```bash
docker compose run --rm -T zam-tv \
  python -m app.services.event_caption_validator \
  --model data/models/Qwen3-4B-Q4_K_M.gguf \
  < caption-candidates.json \
  > caption-validations.json
```

## Ausgabe

```json
[
  {
    "uid": "event-123",
    "approved": true,
    "reason": ""
  }
]
```

Bei einer Ablehnung enthaelt `reason` eine kurze deutsche Begruendung. Eine
leere Caption wird ohne Modellaufruf abgelehnt. Ein Fehler bei einem einzelnen
Kandidaten erzeugt `approved: false` und `error`, ohne den restlichen Durchlauf
abzubrechen.

Generator und Validator koennen mit unterschiedlichen Modellen getestet und
nacheinander ausgefuehrt werden. Die Zusammenfuehrung erfolgt ueber `uid`.
