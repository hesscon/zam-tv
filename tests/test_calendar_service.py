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


class BuildCalendarSlidesTest(TestCase):
    def test_builds_event_slides_for_matching_categories_in_time_window(self) -> None:
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
                slides = calendar_service.build_calendar_slides(item)

        self.assertEqual(3, len(slides))
        self.assertEqual(
            [
                "Pecha Kucha Night Erlangen",
                "Verändert KI die Arbeitswelt?",
                "Gründungscafé (in Kooperation mit Wirtschaftsjunioren Erlangen & FAU Gründungsberatung)",
            ],
            [slide["summary"] for slide in slides],
        )
        self.assertTrue(all(slide["type"] == "calendar_event" for slide in slides))
        self.assertTrue(all(slide["duration"] == 12 for slide in slides))
        self.assertTrue(all(slide["category"] == "Veranstaltung" for slide in slides))
        self.assertEqual(
            "https://www.zam.haus/wp-content/uploads/2025/09/pkerlangen_cover.jpg",
            slides[0]["image_url"],
        )
        self.assertEqual(
            "https://www.zam.haus/programm/pecha-kucha-night-erlangen-937/",
            slides[0]["event_url"],
        )
        self.assertTrue(slides[0]["qr_code_data_uri"].startswith("data:image/svg+xml;base64,"))
        self.assertEqual("2026-03-20T20:20:00+00:00", slides[0]["start_iso"])
        self.assertEqual("Freitag, 20. März 21:20", slides[0]["start_label"])

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
                slides = calendar_service.build_calendar_slides(item)

        self.assertEqual(1, len(slides))
        self.assertEqual("Gründungscafé", slides[0]["summary"])
        self.assertEqual("", slides[0]["image_url"])
        self.assertEqual("Veranstaltung", slides[0]["category"])
        self.assertEqual(20, slides[0]["duration"])
        self.assertEqual("Samstag, 25. April 12:00", slides[0]["start_label"])

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
                slides = calendar_service.build_calendar_slides(item)

        matching_slides = [
            slide
            for slide in slides
            if slide["summary"].startswith("Gründungscafé (Kooperation von ZAM")
        ]
        self.assertEqual(1, len(matching_slides))
        self.assertEqual("2026-07-25T08:00:00+00:00", matching_slides[0]["start_iso"])
        self.assertEqual("Samstag, 25. Juli 10:00", matching_slides[0]["start_label"])

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
                slides = calendar_service.build_calendar_slides(item)

        self.assertEqual(1, len(slides))
        self.assertEqual("Ehrenamtliche Beratung", slides[0]["summary"])
        self.assertEqual("2026-07-30T13:00:00+00:00", slides[0]["start_iso"])
        self.assertEqual("Donnerstag, 30. Juli 15:00", slides[0]["start_label"])

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
                slides = calendar_service.build_calendar_slides(item)

        self.assertEqual(1, len(slides))
        self.assertEqual("Zentralperspektive Grundlagen", slides[0]["summary"])
        self.assertEqual("2026-08-09T08:00:00+00:00", slides[0]["start_iso"])
        self.assertEqual("Sonntag, 9. August 10:00", slides[0]["start_label"])

    def test_formats_labels_in_berlin_timezone(self) -> None:
        self.assertEqual(
            "Sonntag, 9. August 10:00",
            calendar_service._format_start_label(
                datetime(2026, 8, 9, 8, 0, tzinfo=timezone.utc)
            ),
        )
        self.assertEqual(
            "Donnerstag, 12. Februar 15:00",
            calendar_service._format_start_label(
                datetime(2026, 2, 12, 14, 0, tzinfo=timezone.utc)
            ),
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
                calendar_service.build_calendar_slides(item)

    def test_ignores_unsafe_or_missing_event_urls(self) -> None:
        self.assertEqual("", calendar_service._normalize_event_url(None))
        self.assertEqual("", calendar_service._normalize_event_url("javascript:alert(1)"))
        self.assertEqual("", calendar_service._build_qr_code_data_uri(""))
        self.assertEqual(
            "",
            calendar_service._build_qr_code_data_uri("https://example.com/" + "a" * 5000),
        )


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
