from unittest import TestCase

from app.services.screen_heartbeat import ScreenHeartbeat


class ScreenHeartbeatTest(TestCase):
    def test_is_not_fresh_before_first_heartbeat(self) -> None:
        heartbeat = ScreenHeartbeat()

        self.assertFalse(heartbeat.is_fresh())

    def test_expires_after_timeout(self) -> None:
        now = [100.0]
        heartbeat = ScreenHeartbeat(timeout_seconds=600, clock=lambda: now[0])

        heartbeat.record()
        now[0] += 600
        self.assertTrue(heartbeat.is_fresh())

        now[0] += 0.1
        self.assertFalse(heartbeat.is_fresh())
