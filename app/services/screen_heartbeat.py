from collections.abc import Callable
from threading import Lock
from time import monotonic


SCREEN_HEARTBEAT_TIMEOUT_SECONDS = 10 * 60


class ScreenHeartbeat:
    """Remember whether the screen playlist has made recent progress."""

    def __init__(
        self,
        timeout_seconds: int = SCREEN_HEARTBEAT_TIMEOUT_SECONDS,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds muss groesser als 0 sein.")

        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._last_seen: float | None = None
        self._lock = Lock()

    def record(self) -> None:
        with self._lock:
            self._last_seen = self._clock()

    def is_fresh(self) -> bool:
        with self._lock:
            if self._last_seen is None:
                return False
            return self._clock() - self._last_seen <= self._timeout_seconds
