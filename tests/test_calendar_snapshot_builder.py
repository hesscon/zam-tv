from copy import deepcopy
from unittest import TestCase
from unittest.mock import Mock, patch

from app.services.calendar_snapshot_builder import (
    CalendarSnapshotBuilder,
    build_calendar_item_key,
)


CALENDAR_ITEM = {
    "type": "calendar",
    "content": "https://example.com/events.ics",
    "duration": 12,
    "enabled": True,
    "categories": ["Veranstaltung"],
    "days_ahead": 15,
    "fix_mec_timezone": False,
    "caption_generation_enabled": True,
}
CONFIG = {"items": [CALENDAR_ITEM]}


def _event(
    uid: str,
    title: str,
    description: str,
    *,
    start_iso: str = "2026-08-06T18:00:00+00:00",
) -> dict:
    return {
        "uid": uid,
        "title": title,
        "description": description,
        "slide": {
            "type": "calendar_event",
            "duration": 12,
            "summary": title,
            "category": "Veranstaltung",
            "image_url": "",
            "event_url": "",
            "qr_code_data_uri": "",
            "start_iso": start_iso,
            "start_label": "Donnerstag, 6. August 20:00",
        },
    }


class CalendarSnapshotBuilderTest(TestCase):
    def setUp(self) -> None:
        self.worker = Mock()
        self.builder = CalendarSnapshotBuilder(self.worker)

    def test_sends_new_events_in_one_batch_and_merges_results(self) -> None:
        events = [
            _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen."),
            _event("event-2", "Cajon bauen", "Ein Instrument aus Holz bauen."),
        ]
        self.worker.generate.side_effect = lambda requests: [
            {"uid": request["uid"], "caption": f"Caption {index}"}
            for index, request in enumerate(requests, start=1)
        ]

        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=events,
        ):
            snapshot = self.builder.build(CONFIG, {})

        requests = self.worker.generate.call_args.args[0]
        slides = snapshot[build_calendar_item_key(CALENDAR_ITEM)]
        self.assertEqual(2, len(requests))
        self.assertEqual(
            {"event-1", "event-2"},
            {slide["uid"] for slide in slides},
        )
        self.assertEqual(["Caption 1", "Caption 2"], [s["caption"] for s in slides])
        self.assertTrue(all(slide["caption_input_hash"] for slide in slides))
        self.assertTrue(all("description" not in slide for slide in slides))

    def test_reports_each_streamed_result_as_snapshot_progress(self) -> None:
        events = [
            _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen."),
            _event("event-2", "Cajon bauen", "Ein Instrument aus Holz bauen."),
        ]

        def generate(requests):
            yield {"uid": requests[0]["uid"], "caption": "Erste Caption"}
            yield {"uid": requests[1]["uid"], "caption": "Zweite Caption"}

        self.worker.generate.side_effect = generate
        progress = []

        with (
            patch(
                "app.services.calendar_snapshot_builder.build_calendar_events",
                return_value=events,
            ),
            self.assertLogs(
                "app.services.calendar_snapshot_builder",
                level="INFO",
            ) as logs,
        ):
            self.builder.build(
                CONFIG,
                {},
                on_progress=lambda snapshot: progress.append(deepcopy(snapshot)),
            )

        key = build_calendar_item_key(CALENDAR_ITEM)
        first_progress = progress[0][key]
        second_progress = progress[1][key]
        self.assertEqual("Erste Caption", first_progress[0]["caption"])
        self.assertIn("caption_input_hash", first_progress[0])
        self.assertNotIn("caption_input_hash", first_progress[1])
        self.assertEqual("Zweite Caption", second_progress[1]["caption"])
        self.assertIn("caption_input_hash", second_progress[1])
        output = "\n".join(logs.output)
        self.assertIn(
            "Caption erzeugt: uid=event-1 titel='Funkenflug' "
            "caption='Erste Caption'",
            output,
        )
        self.assertIn(
            "Caption erzeugt: uid=event-2 titel='Cajon bauen' "
            "caption='Zweite Caption'",
            output,
        )

    def test_logs_when_worker_decides_no_caption_is_needed(self) -> None:
        event = _event(
            "event-1",
            "Klarer Titel",
            "Eine organisatorische Beschreibung.",
        )
        self.worker.generate.side_effect = lambda requests: iter(
            [{"uid": requests[0]["uid"], "caption": ""}]
        )

        with (
            patch(
                "app.services.calendar_snapshot_builder.build_calendar_events",
                return_value=[event],
            ),
            self.assertLogs(
                "app.services.calendar_snapshot_builder",
                level="INFO",
            ) as logs,
        ):
            self.builder.build(CONFIG, {})

        self.assertIn(
            "Keine Caption erforderlich: uid=event-1 titel='Klarer Titel'",
            "\n".join(logs.output),
        )

    def test_worker_failure_after_progress_keeps_completed_result(self) -> None:
        events = [
            _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen."),
            _event("event-2", "Cajon bauen", "Ein Instrument aus Holz bauen."),
        ]

        def generate(requests):
            yield {"uid": requests[0]["uid"], "caption": "Erste Caption"}
            raise RuntimeError("Worker abgebrochen")

        self.worker.generate.side_effect = generate
        progress = []

        with (
            patch(
                "app.services.calendar_snapshot_builder.build_calendar_events",
                return_value=events,
            ),
            self.assertLogs(
                "app.services.calendar_snapshot_builder",
                level="ERROR",
            ),
        ):
            snapshot = self.builder.build(
                CONFIG,
                {},
                on_progress=lambda value: progress.append(deepcopy(value)),
            )

        slides = snapshot[build_calendar_item_key(CALENDAR_ITEM)]
        self.assertEqual(["Erste Caption", ""], [s["caption"] for s in slides])
        self.assertTrue(all(s["caption_input_hash"] for s in slides))
        self.assertEqual(2, len(progress))

    def test_reuses_unchanged_caption_without_starting_worker(self) -> None:
        event = _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen.")
        self.worker.generate.side_effect = lambda requests: [
            {"uid": requests[0]["uid"], "caption": "Leuchtende Fotos aufnehmen"}
        ]

        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=[event],
        ):
            first_snapshot = self.builder.build(CONFIG, {})
            self.worker.reset_mock()
            second_snapshot = self.builder.build(CONFIG, first_snapshot)

        self.worker.generate.assert_not_called()
        slide = second_snapshot[build_calendar_item_key(CALENDAR_ITEM)][0]
        self.assertEqual("Leuchtende Fotos aufnehmen", slide["caption"])

    def test_only_changed_event_is_sent_to_worker(self) -> None:
        initial_events = [
            _event("event-1", "Unverändert", "Gleiche Beschreibung."),
            _event("event-2", "Alt", "Alte Beschreibung."),
        ]
        self.worker.generate.side_effect = lambda requests: [
            {"uid": request["uid"], "caption": request["title"]}
            for request in requests
        ]

        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=initial_events,
        ):
            previous_snapshot = self.builder.build(CONFIG, {})

        changed_events = [
            initial_events[0],
            _event("event-2", "Neu", "Neue Beschreibung."),
        ]
        self.worker.reset_mock()
        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=changed_events,
        ):
            self.builder.build(CONFIG, previous_snapshot)

        requests = self.worker.generate.call_args.args[0]
        self.assertEqual(1, len(requests))
        self.assertEqual("Neu", requests[0]["title"])

    def test_recurring_occurrences_are_sent_only_once(self) -> None:
        events = [
            _event("series-1", "Offener Treff", "Gemeinsam Projekte bearbeiten."),
            _event(
                "series-1",
                "Offener Treff",
                "Gemeinsam Projekte bearbeiten.",
                start_iso="2026-08-13T18:00:00+00:00",
            ),
        ]
        self.worker.generate.side_effect = lambda requests: [
            {"uid": requests[0]["uid"], "caption": "Gemeinsam Projekte bearbeiten"}
        ]

        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=events,
        ):
            snapshot = self.builder.build(CONFIG, {})

        requests = self.worker.generate.call_args.args[0]
        slides = snapshot[build_calendar_item_key(CALENDAR_ITEM)]
        self.assertEqual(1, len(requests))
        self.assertEqual(
            ["Gemeinsam Projekte bearbeiten", "Gemeinsam Projekte bearbeiten"],
            [slide["caption"] for slide in slides],
        )

    def test_empty_description_is_persisted_without_worker_call(self) -> None:
        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=[_event("event-1", "Klarer Titel", "")],
        ):
            snapshot = self.builder.build(CONFIG, {})

        self.worker.generate.assert_not_called()
        slide = snapshot[build_calendar_item_key(CALENDAR_ITEM)][0]
        self.assertEqual("", slide["caption"])
        self.assertTrue(slide["caption_input_hash"])

    def test_does_not_start_worker_when_caption_generation_is_disabled(self) -> None:
        config = {
            "items": [
                {**CALENDAR_ITEM, "caption_generation_enabled": False},
            ]
        }
        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=[
                _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen."),
            ],
        ):
            snapshot = self.builder.build(config, {})

        self.worker.generate.assert_not_called()
        slide = snapshot[build_calendar_item_key(CALENDAR_ITEM)][0]
        self.assertEqual("", slide["caption"])
        self.assertNotIn("caption_input_hash", slide)

    def test_missing_caption_setting_does_not_start_worker(self) -> None:
        config = {
            "items": [
                {
                    key: value
                    for key, value in CALENDAR_ITEM.items()
                    if key != "caption_generation_enabled"
                }
            ]
        }
        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=[
                _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen."),
            ],
        ):
            self.builder.build(config, {})

        self.worker.generate.assert_not_called()

    def test_generates_caption_after_disabled_setting_is_enabled(self) -> None:
        event = _event(
            "event-1",
            "Funkenflug",
            "Langzeitfotos mit Wunderkerzen.",
        )
        disabled_config = {
            "items": [
                {**CALENDAR_ITEM, "caption_generation_enabled": False},
            ]
        }
        self.worker.generate.side_effect = lambda requests: [
            {"uid": requests[0]["uid"], "caption": "Leuchtende Fotos aufnehmen"}
        ]

        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=[event],
        ):
            disabled_snapshot = self.builder.build(disabled_config, {})
            enabled_snapshot = self.builder.build(CONFIG, disabled_snapshot)

        self.worker.generate.assert_called_once()
        slide = enabled_snapshot[build_calendar_item_key(CALENDAR_ITEM)][0]
        self.assertEqual("Leuchtende Fotos aufnehmen", slide["caption"])

    def test_worker_error_is_logged_and_empty_caption_is_reused(self) -> None:
        event = _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen.")
        self.worker.generate.side_effect = lambda requests: [
            {
                "uid": requests[0]["uid"],
                "caption": "",
                "error": "Modellantwort ungueltig",
            }
        ]

        with (
            patch(
                "app.services.calendar_snapshot_builder.build_calendar_events",
                return_value=[event],
            ),
            self.assertLogs(
                "app.services.calendar_snapshot_builder",
                level="ERROR",
            ) as logs,
        ):
            first_snapshot = self.builder.build(CONFIG, {})

        self.assertIn("uid=event-1", "\n".join(logs.output))
        self.assertIn("Modellantwort ungueltig", "\n".join(logs.output))

        self.worker.reset_mock()
        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events",
            return_value=[event],
        ):
            second_snapshot = self.builder.build(CONFIG, first_snapshot)

        self.worker.generate.assert_not_called()
        slide = second_snapshot[build_calendar_item_key(CALENDAR_ITEM)][0]
        self.assertEqual("", slide["caption"])

    def test_worker_process_failure_logs_event_and_keeps_snapshot_usable(self) -> None:
        event = _event("event-1", "Funkenflug", "Langzeitfotos mit Wunderkerzen.")
        self.worker.generate.side_effect = RuntimeError("Modell fehlt")

        with (
            patch(
                "app.services.calendar_snapshot_builder.build_calendar_events",
                return_value=[event],
            ),
            self.assertLogs(
                "app.services.calendar_snapshot_builder",
                level="ERROR",
            ) as logs,
        ):
            snapshot = self.builder.build(CONFIG, {})

        output = "\n".join(logs.output)
        self.assertIn("Caption-Worker fehlgeschlagen", output)
        self.assertIn("uid=event-1", output)
        self.assertIn("Modell fehlt", output)
        slide = snapshot[build_calendar_item_key(CALENDAR_ITEM)][0]
        self.assertEqual("", slide["caption"])

    def test_disabled_calendar_is_not_loaded(self) -> None:
        disabled_config = {"items": [{**CALENDAR_ITEM, "enabled": False}]}

        with patch(
            "app.services.calendar_snapshot_builder.build_calendar_events"
        ) as load_mock:
            snapshot = self.builder.build(disabled_config, {})

        load_mock.assert_not_called()
        self.worker.generate.assert_not_called()
        self.assertEqual({}, snapshot)
