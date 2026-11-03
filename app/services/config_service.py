from pathlib import Path

import yaml


# Used on first start so the app has a working example even in an empty repo.
DEFAULT_CONFIG = """items:
  - type: image
    content: sample.jpg
    duration: 8
    enabled: false

  - type: web
    content: https://www.openai.com
    duration: 15
    enabled: false

  - type: calendar
    content: https://example.com/calendar.ics
    duration: 15
    enabled: false
    caption_generation_enabled: false
    categories:
      - Veranstaltung
    days_ahead: 14
    fix_mec_timezone: false

  - type: video
    content: sample.mp4
    enabled: false

textecke:
  enabled: false
  content: https://example.com/calendar.ics
  message_url: http://texteck.usr.zam.haus/api/v1/message
  categories:
    - Haupthaus
  fix_mec_timezone: false
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

    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ConfigError(f"Eintrag {index} in `items` muss ein Objekt sein.")

        item_type = item.get("type")
        if item_type not in {"image", "video", "web", "calendar"}:
            raise ConfigError(
                f"Eintrag {index} hat einen ungueltigen Typ. Erlaubt sind image, video, web, calendar."
            )

        if not item.get("content"):
            raise ConfigError(f"Eintrag {index} braucht ein Feld `content`.")

        if item_type != "video" and "duration" not in item:
            raise ConfigError(f"Eintrag {index} vom Typ `{item_type}` braucht `duration`.")

        if item_type == "calendar":
            categories = item.get("categories", [])
            if categories and not isinstance(categories, list):
                raise ConfigError(f"Eintrag {index} vom Typ `calendar` braucht `categories` als Liste.")

            days_ahead = item.get("days_ahead", 14)
            try:
                days_ahead = int(days_ahead)
                if days_ahead < 0:
                    raise ValueError
            except (TypeError, ValueError) as exc:
                raise ConfigError(f"Eintrag {index} vom Typ `calendar` braucht `days_ahead` als Zahl >= 0.") from exc

            item["categories"] = categories
            item["days_ahead"] = days_ahead

            fix_mec_timezone = item.get("fix_mec_timezone", False)
            if not isinstance(fix_mec_timezone, bool):
                raise ConfigError(
                    f"Eintrag {index} vom Typ `calendar` braucht `fix_mec_timezone` als true oder false."
                )
            item["fix_mec_timezone"] = fix_mec_timezone

            caption_generation_enabled = item.get(
                "caption_generation_enabled",
                False,
            )
            if not isinstance(caption_generation_enabled, bool):
                raise ConfigError(
                    f"Eintrag {index} vom Typ `calendar` braucht "
                    "`caption_generation_enabled` als true oder false."
                )
            item["caption_generation_enabled"] = caption_generation_enabled

    _normalize_textecke_config(config)

    return config


def _normalize_textecke_config(config: dict) -> None:
    textecke = config.get("textecke")
    if textecke is None:
        return
    if not isinstance(textecke, dict):
        raise ConfigError("`textecke` muss ein Objekt sein.")

    enabled = textecke.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("`textecke.enabled` muss true oder false sein.")

    content = textecke.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ConfigError("`textecke.content` muss eine ICS-URL sein.")

    message_url = textecke.get("message_url")
    if not isinstance(message_url, str) or not message_url.strip():
        raise ConfigError("`textecke.message_url` muss eine URL sein.")

    categories = textecke.get("categories", [])
    if not isinstance(categories, list) or not all(
        isinstance(category, str) for category in categories
    ):
        raise ConfigError("`textecke.categories` muss eine Liste aus Texten sein.")

    fix_mec_timezone = textecke.get("fix_mec_timezone", False)
    if not isinstance(fix_mec_timezone, bool):
        raise ConfigError(
            "`textecke.fix_mec_timezone` muss true oder false sein."
        )

    textecke["enabled"] = enabled
    textecke["content"] = content.strip()
    textecke["message_url"] = message_url.strip()
    textecke["categories"] = [
        category.strip() for category in categories if category.strip()
    ]
    textecke["fix_mec_timezone"] = fix_mec_timezone
