import logging
from unittest import TestCase

from app.services.recent_log_handler import RecentLogHandler


class RecentLogHandlerTest(TestCase):
    def setUp(self) -> None:
        self.logger = logging.getLogger("recent-log-handler-test")
        self.logger.handlers = []
        self.logger.propagate = False
        self.logger.setLevel(logging.INFO)

    def tearDown(self) -> None:
        self.logger.handlers = []

    def test_keeps_only_the_newest_lines_in_order(self) -> None:
        handler = RecentLogHandler(capacity=2)
        self.logger.addHandler(handler)

        self.logger.info("Erste Meldung")
        self.logger.warning("Zweite Meldung")
        self.logger.error("Dritte Meldung")

        lines = handler.get_lines()
        self.assertEqual(2, len(lines))
        self.assertIn("Zweite Meldung", lines[0])
        self.assertIn("Dritte Meldung", lines[1])
        self.assertNotIn("recent-log-handler-test", "\n".join(lines))

    def test_formats_exceptions_as_one_concise_line(self) -> None:
        handler = RecentLogHandler()
        self.logger.addHandler(handler)

        try:
            raise RuntimeError("Kaputt\nmit Detail")
        except RuntimeError:
            self.logger.exception("Aktualisierung fehlgeschlagen")

        lines = handler.get_lines()
        self.assertEqual(1, len(lines))
        self.assertIn("Aktualisierung fehlgeschlagen", lines[0])
        self.assertNotIn("Traceback", lines[0])
        self.assertNotIn("\n", lines[0])
