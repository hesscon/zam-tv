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
        self.assertEqual("2026-03-20T20:20:00+00:00", slides[0]["start_iso"])

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


def _fixture_response() -> FakeResponse:
    return FakeResponse(FIXTURE_PATH.read_text(encoding="utf-8"))
