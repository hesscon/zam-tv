from pathlib import Path

import yaml


# Used on first start so the app has a working example even in an empty repo.
DEFAULT_CONFIG = """orientation: portrait
rotation_seconds: 10
items:
  - type: image
    title: Beispielbild
    path: sample.jpg
    duration: 8
    enabled: false

  - type: web
    title: OpenAI
    url: https://www.openai.com
    duration: 15
    enabled: false

  - type: calendar
    title: Veranstaltungen
    duration: 15
    enabled: false
    ics_url: https://example.com/calendar.ics
    include_titles: []
    max_events: 5
"""


class ConfigError(Exception):
    pass


def ensure_config_exists(config_path: Path, uploads_dir: Path) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    uploads_dir.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        config_path.write_text(DEFAULT_CONFIG, encoding="utf-8")


def load_config(config_path: Path) -> dict:
    text = config_path.read_text(encoding="utf-8")
    return parse_config(text)


def save_config(config_path: Path, config_text: str) -> None:
    # Normalize trailing whitespace so manual edits stay reasonably tidy.
    normalized = config_text.strip() + "\n"
    config_path.write_text(normalized, encoding="utf-8")


def validate_config_text(config_text: str) -> None:
    parse_config(config_text)


def parse_config(config_text: str) -> dict:
    try:
        config = yaml.safe_load(config_text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML-Fehler: {exc}") from exc

    if not isinstance(config, dict):
        raise ConfigError("Die Konfiguration muss ein YAML-Objekt sein.")

    items = config.get("items", [])
    if not isinstance(items, list):
        raise ConfigError("`items` muss eine Liste sein.")

    # Keep validation intentionally small for V1: just enough to catch obvious mistakes.
    orientation = config.get("orientation", "portrait")
    if orientation not in {"portrait", "landscape"}:
        raise ConfigError("`orientation` muss `portrait` oder `landscape` sein.")

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"Eintrag {index} in `items` muss ein Objekt sein.")

        item_type = item.get("type")
        if item_type not in {"image", "video", "web", "calendar"}:
            raise ConfigError(
                f"Eintrag {index} hat einen ungueltigen Typ. Erlaubt sind image, video, web, calendar."
            )

    return config
