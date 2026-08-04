from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock

from app import create_app


class ViewsTest(TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        config_path = base_dir / "content.yaml"
        uploads_dir = base_dir / "uploads"
        config_path.write_text("items: []\n", encoding="utf-8")
        uploads_dir.mkdir()

        self.app = create_app(start_calendar_cache=False)
        self.app.config.update(
            TESTING=True,
            CONFIG_PATH=config_path,
            UPLOADS_DIR=uploads_dir,
        )
        self.client = self.app.test_client()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_root_redirects_to_admin(self) -> None:
        response = self.client.get("/")

        self.assertEqual(302, response.status_code)
        self.assertEqual("/admin", response.headers["Location"])

    def test_admin_and_screen_remain_available(self) -> None:
        self.assertEqual(200, self.client.get("/admin").status_code)
        self.assertEqual(200, self.client.get("/screen").status_code)

    def test_screen_reads_calendar_slides_from_cache(self) -> None:
        calendar_item = """  - type: calendar
    content: https://example.com/events.ics
    duration: 12
    enabled: true
    categories:
      - Veranstaltung
    days_ahead: 15
    fix_mec_timezone: false
"""
        self.app.config["CONFIG_PATH"].write_text(
            f"items:\n{calendar_item}",
            encoding="utf-8",
        )
        cache = Mock()
        cache.get_slides.return_value = [
            {
                "type": "calendar_event",
                "duration": 12,
                "summary": "Aus dem Cache",
                "category": "Veranstaltung",
                "image_url": "",
                "event_url": "",
                "qr_code_data_uri": "",
                "start_iso": "2026-08-05T10:00:00+00:00",
                "start_label": "Mittwoch, 5. August 12:00",
            }
        ]
        self.app.extensions["calendar_slide_cache"] = cache

        response = self.client.get("/screen")

        self.assertEqual(200, response.status_code)
        cache.get_slides.assert_called_once()
        self.assertIn(b"Aus dem Cache", response.data)
