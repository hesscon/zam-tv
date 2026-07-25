# LLM-Caption-Worker testen

Der Worker liest ein JSON-Array aus `stdin`, laedt das Modell einmal und schreibt die Ergebnisse als JSON nach `stdout`. Das Modell selbst wird per JSON-Schema auf `{"caption":"..."}` beschraenkt. Laufzeiten und Fehler erscheinen auf `stderr`.

## Vorbereitung

Modelldatei auf dem Raspberry Pi herunterladen:

```bash
mkdir -p data/models
curl -L \
  -o data/models/Qwen3-0.6B-Q8_0.gguf \
  "https://huggingface.co/Qwen/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B-Q8_0.gguf?download=true"
```

Die Modelldatei ist etwa 639 MB gross und wird nicht in Git eingecheckt.
Das Docker-Image enthaelt den Worker und `llama-cpp-python`, aber nicht das Modell. Nach dieser Aenderung muss das Image einmal neu gebaut werden:

```bash
docker compose build
```

Fuer bessere Textqualitaet kann alternativ Qwen3-1.7B in Q4_K_M verwendet werden:

```bash
curl -L \
  -o data/models/Qwen3-1.7B-Q4_K_M.gguf \
  "https://huggingface.co/bartowski/Qwen_Qwen3-1.7B-GGUF/resolve/main/Qwen_Qwen3-1.7B-Q4_K_M.gguf"
```

Diese Datei ist etwa 1,28 GB gross und braucht mehr RAM sowie Rechenzeit.

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
  --model data/models/Qwen3-0.6B-Q8_0.gguf \
  < events.json \
  > captions.json
```

Standardmaessig verwendet der Worker zwei CPU-Threads und eine niedrige Temperatur von `0.2`. Fuer Vergleiche auf dem Raspberry Pi koennen beispielsweise `--threads 1`, `--threads 4` oder `--temperature 0.7` gesetzt werden.

Alternativ kann der Worker in einer lokalen Python-Umgebung ausgefuehrt werden:

```bash
pip install -r requirements-llm.txt
python3 -m app.services.event_caption_worker \
  --model data/models/Qwen3-0.6B-Q8_0.gguf \
  < events.json \
  > captions.json
```

## Ausgabe

```json
[
  {
    "uid": "event-123",
    "caption": "Kurze Vortraege zu vielfaeltigen Themen"
  }
]
```

Ein Fehler bei einem einzelnen Event erzeugt eine leere Caption mit `error`, ohne die restlichen Events abzubrechen. Ein unlesbares Eingabe-JSON oder ein fehlendes Modell beendet den Worker mit Exit-Code `1`.
