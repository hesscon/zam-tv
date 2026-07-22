from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app import create_app


class ViewsTest(TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        base_dir = Path(self.temp_dir.name)
        config_path = base_dir / "content.yaml"
        uploads_dir = base_dir / "uploads"
        config_path.write_text("items: []\n", encoding="utf-8")
        uploads_dir.mkdir()

        self.app = create_app()
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
