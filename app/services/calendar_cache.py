import logging
from datetime import timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic

from .calendar_service import build_calendar_slides
from .config_service import load_config


logger = logging.getLogger(__name__)
DEFAULT_REFRESH_INTERVAL = timedelta(minutes=15)
CalendarItemKey = tuple[str, tuple[str, ...], int, str, bool]


class CalendarSlideCache:
    def __init__(
        self,
        config_path: Path,
        refresh_interval: timedelta = DEFAULT_REFRESH_INTERVAL,
    ) -> None:
        self._config_path = config_path
        self._refresh_interval = refresh_interval
        self._snapshot: dict[CalendarItemKey, tuple[dict, ...]] = {}
        self._snapshot_lock = Lock()
        self._refresh_lock = Lock()
        self._thread_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def get_slides(self, item: dict) -> list[dict]:
        key = _build_calendar_item_key(item)
        with self._snapshot_lock:
            return list(self._snapshot.get(key, ()))

    def refresh(self) -> None:
        with self._refresh_lock:
            started_at = monotonic()
            logger.info("Kalender-Cache-Refresh gestartet.")

            config = load_config(self._config_path)
            new_snapshot: dict[CalendarItemKey, tuple[dict, ...]] = {}
            calendar_count = 0

            for item in config.get("items", []):
                if not item.get("enabled", True) or item.get("type") != "calendar":
                    continue

                key = _build_calendar_item_key(item)
                if key not in new_snapshot:
                    new_snapshot[key] = tuple(build_calendar_slides(item))
                    calendar_count += 1

            with self._snapshot_lock:
                self._snapshot = new_snapshot

            slide_count = sum(len(slides) for slides in new_snapshot.values())
            logger.info(
                "Kalender-Cache-Refresh erfolgreich: kalender=%d slides=%d "
                "dauer=%.2fs naechster_refresh_in=%.0fs",
                calendar_count,
                slide_count,
                monotonic() - started_at,
                self._refresh_interval.total_seconds(),
            )

    def start(self) -> None:
        with self._thread_lock:
            if self._thread and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name="calendar-slide-cache",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.refresh()
            except Exception:
                logger.exception("Kalender-Cache konnte nicht aktualisiert werden.")

            self._stop_event.wait(self._refresh_interval.total_seconds())


def _build_calendar_item_key(item: dict) -> CalendarItemKey:
    categories = tuple(
        sorted({value.strip() for value in item.get("categories", []) if value})
    )
    return (
        item["content"],
        categories,
        item.get("days_ahead", 14),
        str(item.get("duration", 15)),
        item.get("fix_mec_timezone", False),
    )
