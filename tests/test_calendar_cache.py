import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from unittest import TestCase
from unittest.mock import patch

from app.services.calendar_cache import CalendarSlideCache


CALENDAR_ITEM = {
    "type": "calendar",
    "content": "https://example.com/events.ics",
    "duration": 12,
    "enabled": True,
    "categories": ["Veranstaltung"],
    "days_ahead": 15,
    "fix_mec_timezone": False,
}


class CalendarSlideCacheTest(TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "content.yaml"
        self.config_path.write_text(
            """items:
  - type: calendar
    content: https://example.com/events.ics
    duration: 12
    enabled: true
    categories:
      - Veranstaltung
    days_ahead: 15
    fix_mec_timezone: false
""",
            encoding="utf-8",
        )
        self.snapshot_path = (
            Path(self.temp_dir.name) / "cache" / "calendar_cache.json"
        )
        self.cache = CalendarSlideCache(self.config_path, self.snapshot_path)

    def tearDown(self) -> None:
        self.cache.stop(timeout=1)
        self.temp_dir.cleanup()

    def test_is_empty_before_first_successful_refresh(self) -> None:
        self.assertEqual([], self.cache.get_slides(CALENDAR_ITEM))

    def test_refresh_atomically_publishes_built_slides(self) -> None:
        slides = [{"type": "calendar_event", "summary": "Test"}]

        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            return_value=slides,
        ):
            self.cache.refresh()

        self.assertEqual(slides, self.cache.get_slides(CALENDAR_ITEM))

    def test_failed_refresh_keeps_previous_snapshot(self) -> None:
        old_slides = [{"type": "calendar_event", "summary": "Alter Stand"}]

        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            return_value=old_slides,
        ):
            self.cache.refresh()

        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            side_effect=RuntimeError("network down"),
        ):
            with self.assertRaisesRegex(RuntimeError, "network down"):
                self.cache.refresh()

        self.assertEqual(old_slides, self.cache.get_slides(CALENDAR_ITEM))

    def test_reads_previous_snapshot_while_refresh_is_building(self) -> None:
        old_slides = [{"type": "calendar_event", "summary": "Alter Stand"}]
        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            return_value=old_slides,
        ):
            self.cache.refresh()

        build_started = Event()
        finish_build = Event()

        def build_slides(item):
            build_started.set()
            finish_build.wait(timeout=1)
            return [{"type": "calendar_event", "summary": "Neuer Stand"}]

        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            side_effect=build_slides,
        ):
            refresh_thread = Thread(target=self.cache.refresh)
            refresh_thread.start()
            self.assertTrue(build_started.wait(timeout=1))
            self.assertEqual(old_slides, self.cache.get_slides(CALENDAR_ITEM))
            finish_build.set()
            refresh_thread.join(timeout=1)

        self.assertFalse(refresh_thread.is_alive())
        self.assertEqual(
            "Neuer Stand",
            self.cache.get_slides(CALENDAR_ITEM)[0]["summary"],
        )

    def test_disabled_calendar_is_not_built(self) -> None:
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "enabled: true",
                "enabled: false",
            ),
            encoding="utf-8",
        )

        with patch("app.services.calendar_cache.build_calendar_slides") as build_mock:
            self.cache.refresh()

        build_mock.assert_not_called()
        self.assertEqual([], self.cache.get_slides(CALENDAR_ITEM))

    def test_background_thread_refreshes_immediately(self) -> None:
        refreshed = Event()

        def build_slides(item):
            refreshed.set()
            return [{"type": "calendar_event", "summary": "Neu"}]

        self.cache = CalendarSlideCache(
            self.config_path,
            self.snapshot_path,
            refresh_interval=timedelta(hours=1),
        )
        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            side_effect=build_slides,
        ):
            self.cache.start()
            self.assertTrue(refreshed.wait(timeout=1))
            self.cache.stop(timeout=1)

        self.assertEqual("Neu", self.cache.get_slides(CALENDAR_ITEM)[0]["summary"])

    def test_successful_refresh_logs_result_and_next_interval(self) -> None:
        self.cache = CalendarSlideCache(
            self.config_path,
            self.snapshot_path,
            refresh_interval=timedelta(seconds=60),
        )

        with (
            patch(
                "app.services.calendar_cache.build_calendar_slides",
                return_value=[
                    {"type": "calendar_event", "summary": "Eins"},
                    {"type": "calendar_event", "summary": "Zwei"},
                ],
            ),
            self.assertLogs("app.services.calendar_cache", level="INFO") as logs,
        ):
            self.cache.refresh()

        output = "\n".join(logs.output)
        self.assertIn("Kalender-Cache-Refresh gestartet.", output)
        self.assertIn(
            "Kalender-Cache-Datei aktualisiert: kalender=1 slides=2",
            output,
        )
        self.assertIn("kalender=1 slides=2", output)
        self.assertIn("naechster_refresh_in=60s", output)

    def test_returned_list_cannot_replace_cached_list(self) -> None:
        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            return_value=[{"type": "calendar_event", "summary": "Test"}],
        ):
            self.cache.refresh()

        returned_slides = self.cache.get_slides(CALENDAR_ITEM)
        returned_slides.clear()

        self.assertEqual(1, len(self.cache.get_slides(CALENDAR_ITEM)))

    def test_refresh_persists_snapshot_that_a_new_cache_loads(self) -> None:
        slides = [
            {
                "type": "calendar_event",
                "duration": 12,
                "summary": "Persistiert",
            }
        ]
        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            return_value=slides,
        ):
            self.cache.refresh()

        payload = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        loaded_cache = CalendarSlideCache(self.config_path, self.snapshot_path)

        self.assertEqual(1, payload["version"])
        self.assertEqual(
            "calendar_event",
            payload["entries"][0]["slides"][0]["type"],
        )
        self.assertEqual(slides, loaded_cache.get_slides(CALENDAR_ITEM))

    def test_invalid_snapshot_is_ignored(self) -> None:
        self.snapshot_path.parent.mkdir(parents=True)
        self.snapshot_path.write_text("{ungueltig", encoding="utf-8")

        with self.assertLogs("app.services.calendar_cache", level="WARNING"):
            loaded_cache = CalendarSlideCache(self.config_path, self.snapshot_path)

        self.assertEqual([], loaded_cache.get_slides(CALENDAR_ITEM))

    def test_failed_refresh_does_not_overwrite_persisted_snapshot(self) -> None:
        old_slides = [{"type": "calendar_event", "summary": "Alter Stand"}]
        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            return_value=old_slides,
        ):
            self.cache.refresh()
        persisted_before_failure = self.snapshot_path.read_text(encoding="utf-8")

        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            side_effect=RuntimeError("network down"),
        ):
            with self.assertRaisesRegex(RuntimeError, "network down"):
                self.cache.refresh()

        self.assertEqual(
            persisted_before_failure,
            self.snapshot_path.read_text(encoding="utf-8"),
        )

    def test_file_write_failure_keeps_previous_memory_snapshot(self) -> None:
        old_slides = [{"type": "calendar_event", "summary": "Alter Stand"}]
        with patch(
            "app.services.calendar_cache.build_calendar_slides",
            return_value=old_slides,
        ):
            self.cache.refresh()

        with (
            patch(
                "app.services.calendar_cache.build_calendar_slides",
                return_value=[{"type": "calendar_event", "summary": "Neuer Stand"}],
            ),
            patch(
                "app.services.calendar_cache.os.replace",
                side_effect=OSError("disk full"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.cache.refresh()

        self.assertEqual(old_slides, self.cache.get_slides(CALENDAR_ITEM))
        self.assertFalse(
            self.snapshot_path.with_name(".calendar_cache.json.tmp").exists()
        )
