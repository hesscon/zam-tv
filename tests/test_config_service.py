import importlib.util
from pathlib import Path
from unittest import TestCase

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "config_service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("config_service", MODULE_PATH)
config_service = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE_SPEC.loader.exec_module(config_service)


class ParseConfigTest(TestCase):
    def test_normalizes_textecke_config(self) -> None:
        config = config_service.parse_config(
            """
textecke:
  enabled: true
  content: https://example.com/events.ics
  message_url: http://texteck.example/api/v1/message
  categories:
    - Haupthaus
"""
        )

        textecke = config["textecke"]
        self.assertTrue(textecke["enabled"])
        self.assertEqual(["Haupthaus"], textecke["categories"])
        self.assertFalse(textecke["fix_mec_timezone"])

    def test_accepts_config_without_textecke(self) -> None:
        self.assertEqual({"items": []}, config_service.parse_config("items: []"))

    def test_rejects_invalid_textecke_settings(self) -> None:
        invalid_configs = (
            ('enabled: "yes"', "enabled"),
            ("enabled: false", "content"),
            (
                "enabled: false\n  content: https://example.com/events.ics",
                "message_url",
            ),
            (
                """enabled: false
  content: https://example.com/events.ics
  message_url: http://texteck.example/api/v1/message
  categories: Haupthaus""",
                "categories",
            ),
        )

        for body, expected_message in invalid_configs:
            with self.subTest(body=body):
                with self.assertRaisesRegex(
                    config_service.ConfigError,
                    expected_message,
                ):
                    config_service.parse_config(f"textecke:\n  {body}\n")

    def test_normalizes_calendar_defaults(self) -> None:
        config = config_service.parse_config(
            """
items:
  - type: calendar
    content: https://example.com/events.ics
    duration: 15
"""
        )

        item = config["items"][0]
        self.assertEqual([], item["categories"])
        self.assertEqual(14, item["days_ahead"])
        self.assertFalse(item["fix_mec_timezone"])
        self.assertFalse(item["caption_generation_enabled"])

    def test_accepts_mec_timezone_fix_for_calendar(self) -> None:
        config = config_service.parse_config(
            """
items:
  - type: calendar
    content: https://example.com/events.ics
    duration: 15
    fix_mec_timezone: true
"""
        )

        self.assertTrue(config["items"][0]["fix_mec_timezone"])

    def test_rejects_non_boolean_mec_timezone_fix(self) -> None:
        with self.assertRaisesRegex(config_service.ConfigError, "true oder false"):
            config_service.parse_config(
                """
items:
  - type: calendar
    content: https://example.com/events.ics
    duration: 15
    fix_mec_timezone: "-1"
"""
            )

    def test_accepts_enabled_caption_generation_for_calendar(self) -> None:
        config = config_service.parse_config(
            """
items:
  - type: calendar
    content: https://example.com/events.ics
    duration: 15
    caption_generation_enabled: true
"""
        )

        self.assertTrue(config["items"][0]["caption_generation_enabled"])

    def test_rejects_non_boolean_caption_generation_setting(self) -> None:
        with self.assertRaisesRegex(
            config_service.ConfigError,
            "caption_generation_enabled.*true oder false",
        ):
            config_service.parse_config(
                """
items:
  - type: calendar
    content: https://example.com/events.ics
    duration: 15
    caption_generation_enabled: "yes"
"""
            )
