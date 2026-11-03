from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "mec-events.ics"
)
MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "calendar_service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("calendar_service", MODULE_PATH)
calendar_service = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC and MODULE_SPEC.loader
MODULE_SPEC.loader.exec_module(calendar_service)


class FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self) -> None:
        return None


class BuildCalendarEventsTest(TestCase):
    def test_exposes_uid_and_description_for_caption_processing(self) -> None:
        item = {
            "content": "https://example.com/events.ics",
            "duration": 12,
            "categories": ["Veranstaltung"],
            "days_ahead": 15,
        }

        with patch.object(calendar_service.requests, "get", return_value=_fixture_response()):
            events = calendar_service.build_calendar_events(
                item,
                now=datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc),
            )

        self.assertTrue(events[0]["uid"])
        self.assertEqual(
            "Pecha Kucha Night Erlangen",
            events[0]["title"],
        )
        self.assertTrue(events[0]["description"])
        self.assertIn("Veranstaltung", events[0]["categories"])
        self.assertIsInstance(events[0]["start"], datetime)
        self.assertIsInstance(events[0]["end"], datetime)

    def test_builds_normalized_events_for_matching_categories(self) -> None:
        item = {
            "content": "https://example.com/events.ics",
            "duration": 12,
            "categories": ["Veranstaltung"],
            "days_ahead": 15,
        }

        with patch.object(calendar_service.requests, "get", return_value=_fixture_response()):
            with patch.object(
                calendar_service,
                "_utc_now",
                return_value=datetime(2026, 3, 14, 0, 0, tzinfo=timezone.utc),
            ):
                events = calendar_service.build_calendar_events(item)

        self.assertEqual(3, len(events))
        self.assertEqual(
            [
                "Pecha Kucha Night Erlangen",
                "Verändert KI die Arbeitswelt?",
                "Gründungscafé (in Kooperation mit Wirtschaftsjunioren Erlangen & FAU Gründungsberatung)",
            ],
            [event["title"] for event in events],
        )
        self.assertTrue(
            all("Veranstaltung" in event["categories"] for event in events)
        )
        self.assertEqual(
            "https://www.zam.haus/wp-content/uploads/2025/09/pkerlangen_cover.jpg",
            events[0]["image_url"],
        )
        self.assertEqual(
            "https://www.zam.haus/programm/pecha-kucha-night-erlangen-937/",
            events[0]["event_url"],
        )
        self.assertEqual(
            "2026-03-20T20:20:00+00:00",
            events[0]["start"].isoformat(),
        )
        self.assertEqual(
            "2026-03-20T22:00:00+00:00",
            events[0]["end"].isoformat(),
        )

    def test_keeps_event_without_attach_and_uses_empty_image_url(self) -> None:
        item = {
            "content": "https://example.com/events.ics",
            "duration": 20,
            "categories": ["Veranstaltung"],
            "days_ahead": 10,
        }

        with patch.object(calendar_service.requests, "get", return_value=_fixture_response()):
            with patch.object(
                calendar_service,
                "_utc_now",
                return_value=datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc),
            ):
                events = calendar_service.build_calendar_events(item)

        self.assertEqual(1, len(events))
        self.assertEqual("Gründungscafé", events[0]["title"])
        self.assertEqual("", events[0]["image_url"])
        self.assertIn("Veranstaltung", events[0]["categories"])

    def test_expands_rdate_occurrence_in_time_window(self) -> None:
        item = {
            "content": "https://example.com/events.ics",
            "duration": 12,
            "categories": ["Veranstaltung", "Haupthaus"],
            "days_ahead": 5,
        }

        with patch.object(calendar_service.requests, "get", return_value=_rdate_fixture_response()):
            with patch.object(
                calendar_service,
                "_utc_now",
                return_value=datetime(2026, 7, 25, 7, 0, tzinfo=timezone.utc),
            ):
                events = calendar_service.build_calendar_events(item)

        matching_events = [
            event
            for event in events
            if event["title"].startswith("Gründungscafé (Kooperation von ZAM")
        ]
        self.assertEqual(1, len(matching_events))
        self.assertEqual(
            "2026-07-25T08:00:00+00:00",
            matching_events[0]["start"].isoformat(),
        )
        self.assertEqual(
            "2026-07-25T10:00:00+00:00",
            matching_events[0]["end"].isoformat(),
        )

    def test_keeps_only_next_occurrence_of_recurring_event(self) -> None:
        item = {
            "content": "https://example.com/weekly-events.ics",
            "duration": 12,
            "categories": ["Veranstaltung"],
            "days_ahead": 20,
        }

        with patch.object(
            calendar_service.requests,
            "get",
            return_value=_weekly_fixture_response(),
        ):
            events = calendar_service.build_calendar_events(
                item,
                now=datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(1, len(events))
        self.assertEqual("Offener Treff", events[0]["title"])
        self.assertEqual(
            "2026-08-03T18:00:00+00:00",
            events[0]["start"].isoformat(),
        )

    def test_includes_event_that_is_still_running(self) -> None:
        item = {
            "content": "https://example.com/events.ics",
            "categories": ["Haupthaus"],
            "days_ahead": 7,
        }
        response = FakeResponse(
            """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:ongoing@example.com
DTSTART:20260821T090000Z
DTEND:20260821T120000Z
SUMMARY:Laufender Termin
CATEGORIES:Haupthaus
END:VEVENT
END:VCALENDAR
"""
        )

        with patch.object(calendar_service.requests, "get", return_value=response):
            events = calendar_service.build_calendar_events(
                item,
                now=datetime(2026, 8, 21, 10, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(1, len(events))
        self.assertEqual("Laufender Termin", events[0]["title"])

    def test_shows_following_occurrence_at_previous_end_time(self) -> None:
        item = {
            "content": "https://example.com/weekly-events.ics",
            "duration": 12,
            "categories": ["Veranstaltung"],
            "days_ahead": 20,
        }

        with patch.object(
            calendar_service.requests,
            "get",
            return_value=_weekly_fixture_response(),
        ):
            events = calendar_service.build_calendar_events(
                item,
                now=datetime(2026, 8, 3, 20, 0, tzinfo=timezone.utc),
            )

        self.assertEqual(1, len(events))
        self.assertEqual(
            "2026-08-17T18:00:00+00:00",
            events[0]["start"].isoformat(),
        )

    def test_mec_timezone_fix_corrects_winter_series_before_expansion(self) -> None:
        item = {
            "content": "https://example.com/mec-events.ics",
            "duration": 12,
            "categories": ["Beratung"],
            "days_ahead": 2,
            "fix_mec_timezone": True,
        }

        with patch.object(
            calendar_service.requests,
            "get",
            return_value=_mec_timezone_fixture_response(),
        ):
            with patch.object(
                calendar_service,
                "_utc_now",
                return_value=datetime(2026, 7, 29, 0, 0, tzinfo=timezone.utc),
            ):
                events = calendar_service.build_calendar_events(item)

        self.assertEqual(1, len(events))
        self.assertEqual("Ehrenamtliche Beratung", events[0]["title"])
        self.assertEqual(
            "2026-07-30T13:00:00+00:00",
            events[0]["start"].isoformat(),
        )
        self.assertEqual(
            "2026-07-30T15:00:00+00:00",
            events[0]["end"].isoformat(),
        )

    def test_mec_timezone_fix_corrects_summer_event(self) -> None:
        item = {
            "content": "https://example.com/mec-events.ics",
            "duration": 12,
            "categories": ["Workshop"],
            "days_ahead": 2,
            "fix_mec_timezone": True,
        }

        with patch.object(
            calendar_service.requests,
            "get",
            return_value=_mec_timezone_fixture_response(),
        ):
            with patch.object(
                calendar_service,
                "_utc_now",
                return_value=datetime(2026, 8, 8, 0, 0, tzinfo=timezone.utc),
            ):
                events = calendar_service.build_calendar_events(item)

        self.assertEqual(1, len(events))
        self.assertEqual("Zentralperspektive Grundlagen", events[0]["title"])
        self.assertEqual(
            "2026-08-09T08:00:00+00:00",
            events[0]["start"].isoformat(),
        )
        self.assertEqual(
            "2026-08-09T10:30:00+00:00",
            events[0]["end"].isoformat(),
        )

    def test_mec_timezone_fix_corrects_local_rdate_and_exdate_values(self) -> None:
        calendar = calendar_service.Calendar.from_ical(
            """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:additional-dates@example.com
DTSTART;TZID=Europe/Berlin:20260801T120000
RDATE;TZID=Europe/Berlin:20260809T120000,20260816T120000
EXDATE;TZID=Europe/Berlin:20260816T120000
END:VEVENT
END:VCALENDAR
"""
        )

        calendar_service._apply_mec_timezone_fix(calendar)

        event = calendar.walk("VEVENT")[0]
        self.assertEqual("10:00:00", event["DTSTART"].dt.time().isoformat())
        self.assertEqual(
            ["10:00:00", "10:00:00"],
            [value.dt.time().isoformat() for value in event["RDATE"].dts],
        )
        self.assertEqual(
            ["10:00:00"],
            [value.dt.time().isoformat() for value in event["EXDATE"].dts],
        )

    def test_raises_fetch_error_for_the_cache_to_handle(self) -> None:
        item = {
            "content": "https://example.com/events.ics",
            "duration": 12,
            "categories": ["Veranstaltung"],
            "days_ahead": 15,
        }

        with patch.object(calendar_service.requests, "get", side_effect=Exception("network down")):
            with self.assertRaisesRegex(Exception, "network down"):
                calendar_service.build_calendar_events(item)

    def test_ignores_unsafe_or_missing_event_urls(self) -> None:
        self.assertEqual("", calendar_service._normalize_event_url(None))
        self.assertEqual("", calendar_service._normalize_event_url("javascript:alert(1)"))

    def test_skips_event_with_non_positive_duration(self) -> None:
        item = {
            "content": "https://example.com/events.ics",
            "categories": ["Haupthaus"],
            "days_ahead": 7,
        }
        response = FakeResponse(
            """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:invalid-duration@example.com
DTSTART:20260822T150000Z
DTEND:20260822T150000Z
SUMMARY:Fehlerhafter Termin
CATEGORIES:Haupthaus
END:VEVENT
END:VCALENDAR
"""
        )

        with (
            patch.object(calendar_service.requests, "get", return_value=response),
            self.assertLogs("calendar_service", level="WARNING") as logs,
        ):
            events = calendar_service.build_calendar_events(
                item,
                now=datetime(2026, 8, 21, 0, 0, tzinfo=timezone.utc),
            )

        self.assertEqual([], events)
        self.assertIn("nicht positiver Dauer", "\n".join(logs.output))


def _fixture_response() -> FakeResponse:
    return FakeResponse(FIXTURE_PATH.read_text(encoding="utf-8"))


def _rdate_fixture_response() -> FakeResponse:
    return FakeResponse(
        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ZAM Test//DE
BEGIN:VEVENT
UID:gruendungscafe@example.com
DTSTART;TZID=Europe/Berlin:20260328T110000
DTEND;TZID=Europe/Berlin:20260328T130000
RDATE;VALUE=PERIOD:20260725T080000Z/20260725T100000Z
SUMMARY:Gründungscafé (Kooperation von ZAM und Partnern)
URL:https://www.zam.haus/programm/zam-gruendungscafe-1/
CATEGORIES:Haupthaus,Mitmachen,Veranstaltung
END:VEVENT
END:VCALENDAR
"""
    )


def _mec_timezone_fixture_response() -> FakeResponse:
    return FakeResponse(
        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//WordPress - MEC Test//EN
BEGIN:VEVENT
UID:beratung@example.com
DTSTART;TZID=Europe/Berlin:20260212T160000
DTEND;TZID=Europe/Berlin:20260212T180000
RRULE:FREQ=WEEKLY
SUMMARY:Ehrenamtliche Beratung
CATEGORIES:Beratung
END:VEVENT
BEGIN:VEVENT
UID:zentralperspektive@example.com
DTSTART;TZID=Europe/Berlin:20260809T120000
DTEND;TZID=Europe/Berlin:20260809T143000
SUMMARY:Zentralperspektive Grundlagen
CATEGORIES:Workshop
END:VEVENT
END:VCALENDAR
"""
    )


def _weekly_fixture_response() -> FakeResponse:
    return FakeResponse(
        """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//ZAM Test//DE
BEGIN:VEVENT
UID:offener-treff@example.com
DTSTART:20260803T180000Z
DTEND:20260803T200000Z
RRULE:FREQ=WEEKLY
EXDATE:20260810T180000Z
SUMMARY:Offener Treff
CATEGORIES:Veranstaltung
END:VEVENT
END:VCALENDAR
"""
    )
