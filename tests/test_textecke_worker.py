from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import Mock

from app.services.textecke_worker import (
    DEFAULT_TEXT,
    HTTP_TIMEOUT_SECONDS,
    MAX_MESSAGE_BYTES,
    SEARCH_DAYS,
    TexteckeWorker,
    build_message,
    select_current_or_next_event,
)


NOW = datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc)


def _event(
    title: str,
    start: datetime,
    end: datetime,
    uid: str = "event-1",
) -> dict:
    return {
        "uid": uid,
        "title": title,
        "description": "",
        "categories": ["Haupthaus"],
        "image_url": "",
        "event_url": "",
        "start": start,
        "end": end,
    }


class TexteckeMessageTest(TestCase):
    def test_formats_future_and_current_event_in_berlin_timezone(self) -> None:
        future = _event(
            "Repair Cafe",
            datetime(2026, 8, 22, 13, 0, tzinfo=timezone.utc),
            datetime(2026, 8, 22, 16, 0, tzinfo=timezone.utc),
        )
        current = _event(
            "Repair Cafe",
            NOW - timedelta(minutes=30),
            NOW + timedelta(hours=1),
        )

        self.assertEqual("SA 15:00 · Repair Cafe", build_message(future, NOW))
        self.assertEqual("JETZT · Repair Cafe", build_message(current, NOW))
        self.assertEqual(DEFAULT_TEXT, build_message(None, NOW))

    def test_truncates_at_a_word_boundary_within_utf8_byte_limit(self) -> None:
        event = _event(
            "Wörter " * 100,
            NOW + timedelta(days=1),
            NOW + timedelta(days=1, hours=2),
        )

        message = build_message(event, NOW)

        self.assertLessEqual(len(message.encode("utf-8")), MAX_MESSAGE_BYTES)
        self.assertFalse(message.endswith("Wör"))
        self.assertTrue(message.endswith("Wörter"))

    def test_selects_first_current_event_before_future_events(self) -> None:
        first_current = _event(
            "Erster",
            NOW - timedelta(hours=2),
            NOW + timedelta(hours=2),
            uid="first",
        )
        second_current = _event(
            "Zweiter",
            NOW - timedelta(hours=1),
            NOW + timedelta(hours=1),
            uid="second",
        )
        future = _event(
            "Spaeter",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1, hours=1),
            uid="future",
        )

        selected = select_current_or_next_event(
            [first_current, second_current, future],
            NOW,
        )

        self.assertIs(first_current, selected)


class TexteckeWorkerTest(TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "content.yaml"
        self.config_path.write_text(
            """textecke:
  enabled: true
  content: https://example.com/events.ics
  message_url: http://texteck.example/api/v1/message
  categories:
    - Haupthaus
  fix_mec_timezone: true
items: []
""",
            encoding="utf-8",
        )
        self.event_loader = Mock()
        self.http_post = Mock()
        self.http_post.return_value.raise_for_status.return_value = None
        self.worker = TexteckeWorker(
            self.config_path,
            event_loader=self.event_loader,
            http_post=self.http_post,
        )

    def tearDown(self) -> None:
        self.worker.stop(timeout=1)
        self.temp_dir.cleanup()

    def test_refresh_loads_independent_source_and_posts_next_event(self) -> None:
        event = _event(
            "Repair Cafe",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1, hours=2),
        )
        self.event_loader.return_value = [event]

        self.assertTrue(self.worker.refresh(NOW))

        source_config, load_now = self.event_loader.call_args.args
        self.assertEqual("https://example.com/events.ics", source_config["content"])
        self.assertEqual(["Haupthaus"], source_config["categories"])
        self.assertEqual(SEARCH_DAYS, source_config["days_ahead"])
        self.assertTrue(source_config["fix_mec_timezone"])
        self.assertEqual(NOW, load_now)
        self.http_post.assert_called_once_with(
            "http://texteck.example/api/v1/message",
            json={"text": "SA 12:00 · Repair Cafe"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )

    def test_background_thread_refreshes_immediately(self) -> None:
        loaded = Event()

        def load_events(config, now):
            loaded.set()
            return []

        self.worker = TexteckeWorker(
            self.config_path,
            event_loader=load_events,
            http_post=self.http_post,
        )

        self.worker.start()

        self.assertTrue(loaded.wait(timeout=1))
        self.worker.stop(timeout=1)
        self.assertFalse(self.worker._thread.is_alive())

    def test_unchanged_refresh_does_not_post_again(self) -> None:
        self.event_loader.return_value = [
            _event(
                "Repair Cafe",
                NOW + timedelta(days=1),
                NOW + timedelta(days=1, hours=2),
            )
        ]

        self.worker.refresh(NOW)
        self.worker.refresh(NOW + timedelta(minutes=15))

        self.assertEqual(1, self.http_post.call_count)

    def test_posts_now_message_when_application_starts_during_event(self) -> None:
        self.event_loader.return_value = [
            _event(
                "Repair Cafe",
                NOW - timedelta(minutes=30),
                NOW + timedelta(hours=1),
            )
        ]

        self.worker.refresh(NOW)

        self.assertEqual(
            {"text": "JETZT · Repair Cafe"},
            self.http_post.call_args.kwargs["json"],
        )

    def test_posts_default_after_successful_empty_calendar(self) -> None:
        self.event_loader.return_value = []

        self.worker.refresh(NOW)

        self.assertEqual(
            {"text": DEFAULT_TEXT},
            self.http_post.call_args.kwargs["json"],
        )

    def test_failed_initial_calendar_load_does_not_post(self) -> None:
        self.event_loader.side_effect = RuntimeError("network down")

        with self.assertLogs("app.services.textecke_worker", level="ERROR"):
            self.assertFalse(self.worker.refresh(NOW))

        self.http_post.assert_not_called()

    def test_failed_calendar_load_schedules_retry_after_five_minutes(self) -> None:
        self.event_loader.side_effect = RuntimeError("network down")

        with self.assertLogs("app.services.textecke_worker", level="ERROR"):
            next_refresh, transition = self.worker._process_due_actions(
                NOW,
                NOW,
                None,
            )

        self.assertEqual(NOW + timedelta(minutes=5), next_refresh)
        self.assertIsNone(transition)

    def test_failed_post_is_retried_after_five_minutes(self) -> None:
        self.event_loader.return_value = []
        self.http_post.side_effect = [
            RuntimeError("offline"),
            Mock(raise_for_status=Mock()),
        ]

        with self.assertLogs("app.services.textecke_worker", level="ERROR"):
            self.worker.refresh(NOW)
        self.worker.refresh(NOW + timedelta(minutes=4))
        self.worker.refresh(NOW + timedelta(minutes=5))

        self.assertEqual(2, self.http_post.call_count)

    def test_disabled_integration_does_not_load_or_post(self) -> None:
        self.config_path.write_text(
            self.config_path.read_text(encoding="utf-8").replace(
                "enabled: true",
                "enabled: false",
            ),
            encoding="utf-8",
        )

        self.assertTrue(self.worker.refresh(NOW))

        self.event_loader.assert_not_called()
        self.http_post.assert_not_called()

    def test_next_transition_is_start_then_end(self) -> None:
        event = _event(
            "Repair Cafe",
            NOW + timedelta(hours=1),
            NOW + timedelta(hours=3),
        )
        self.event_loader.return_value = [event]
        self.worker.refresh(NOW)

        self.assertEqual(
            (event["start"], "start"),
            self.worker._next_transition(NOW),
        )
        self.assertEqual(
            (event["end"], "end"),
            self.worker._next_transition(event["start"]),
        )

    def test_start_uses_cached_event_and_end_refreshes_calendar(self) -> None:
        current = _event(
            "Workshop",
            NOW + timedelta(minutes=5),
            NOW + timedelta(minutes=10),
        )
        following = _event(
            "Repair Cafe",
            NOW + timedelta(days=1),
            NOW + timedelta(days=1, hours=2),
            uid="event-2",
        )
        self.event_loader.side_effect = [[current], [following]]

        next_refresh, transition = self.worker._process_due_actions(
            NOW,
            NOW,
            None,
        )
        next_refresh, transition = self.worker._process_due_actions(
            current["start"],
            next_refresh,
            transition,
        )

        self.assertEqual(1, self.event_loader.call_count)
        self.assertEqual(
            {"text": "JETZT · Workshop"},
            self.http_post.call_args.kwargs["json"],
        )

        self.worker._process_due_actions(
            current["end"],
            next_refresh,
            transition,
        )

        self.assertEqual(2, self.event_loader.call_count)
        self.assertEqual(
            {"text": "SA 12:00 · Repair Cafe"},
            self.http_post.call_args.kwargs["json"],
        )
