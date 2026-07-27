import importlib.util
from pathlib import Path
from unittest import TestCase

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "config_service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("config_service", MODULE_PATH)
config_service = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE_SPEC.loader.exec_module(config_service)


class ParseConfigTest(TestCase):
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
