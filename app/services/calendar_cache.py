import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from time import monotonic

from .calendar_service import build_calendar_slides
from .config_service import load_config


logger = logging.getLogger(__name__)
DEFAULT_REFRESH_INTERVAL = timedelta(minutes=15)
SNAPSHOT_VERSION = 1
CalendarItemKey = tuple[str, tuple[str, ...], int, str, bool]


class CalendarSlideCache:
    def __init__(
        self,
        config_path: Path,
        snapshot_path: Path,
        refresh_interval: timedelta = DEFAULT_REFRESH_INTERVAL,
    ) -> None:
        self._config_path = config_path
        self._snapshot_path = snapshot_path
        self._refresh_interval = refresh_interval
        self._snapshot: dict[CalendarItemKey, tuple[dict, ...]] = {}
        self._snapshot_lock = Lock()
        self._refresh_lock = Lock()
        self._thread_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._load_snapshot()

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

            refreshed_at = datetime.now(timezone.utc)
            self._write_snapshot(new_snapshot, refreshed_at)

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

    def _load_snapshot(self) -> None:
        if not self._snapshot_path.exists():
            return

        try:
            payload = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
            snapshot, refreshed_at = _deserialize_snapshot(payload)
        except (OSError, ValueError, TypeError, KeyError):
            logger.warning(
                "Kalender-Cache-Datei ist ungueltig und wird ignoriert: %s",
                self._snapshot_path,
                exc_info=True,
            )
            return

        self._snapshot = snapshot
        logger.info(
            "Kalender-Cache aus Datei geladen: kalender=%d slides=%d stand=%s",
            len(snapshot),
            sum(len(slides) for slides in snapshot.values()),
            refreshed_at,
        )

    def _write_snapshot(
        self,
        snapshot: dict[CalendarItemKey, tuple[dict, ...]],
        refreshed_at: datetime,
    ) -> None:
        payload = _serialize_snapshot(snapshot, refreshed_at)
        self._snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._snapshot_path.with_name(
            f".{self._snapshot_path.name}.tmp"
        )

        try:
            with temporary_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_path, self._snapshot_path)
        finally:
            temporary_path.unlink(missing_ok=True)

        logger.info(
            "Kalender-Cache-Datei aktualisiert: kalender=%d slides=%d pfad=%s",
            len(snapshot),
            sum(len(slides) for slides in snapshot.values()),
            self._snapshot_path,
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


def _serialize_snapshot(
    snapshot: dict[CalendarItemKey, tuple[dict, ...]],
    refreshed_at: datetime,
) -> dict:
    return {
        "version": SNAPSHOT_VERSION,
        "refreshed_at": refreshed_at.isoformat().replace("+00:00", "Z"),
        "entries": [
            {
                "key": {
                    "content": key[0],
                    "categories": list(key[1]),
                    "days_ahead": key[2],
                    "duration": key[3],
                    "fix_mec_timezone": key[4],
                },
                "slides": list(slides),
            }
            for key, slides in snapshot.items()
        ],
    }


def _deserialize_snapshot(
    payload: dict,
) -> tuple[dict[CalendarItemKey, tuple[dict, ...]], str]:
    if not isinstance(payload, dict):
        raise ValueError("Kalender-Cache muss ein JSON-Objekt sein.")
    if payload.get("version") != SNAPSHOT_VERSION:
        raise ValueError("Unbekannte Kalender-Cache-Version.")

    refreshed_at = payload.get("refreshed_at")
    entries = payload.get("entries")
    if not isinstance(refreshed_at, str) or not isinstance(entries, list):
        raise ValueError("Kalender-Cache-Metadaten sind ungueltig.")

    snapshot: dict[CalendarItemKey, tuple[dict, ...]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Kalender-Cache-Eintrag ist ungueltig.")

        key_data = entry.get("key")
        slides = entry.get("slides")
        if not isinstance(key_data, dict) or not isinstance(slides, list):
            raise ValueError("Kalender-Cache-Eintrag ist unvollstaendig.")
        if not all(isinstance(slide, dict) for slide in slides):
            raise ValueError("Kalender-Cache enthaelt ungueltige Slides.")
        if (
            not isinstance(key_data.get("content"), str)
            or not isinstance(key_data.get("categories"), list)
            or not all(
                isinstance(category, str)
                for category in key_data.get("categories", [])
            )
            or not isinstance(key_data.get("days_ahead"), int)
            or isinstance(key_data.get("days_ahead"), bool)
            or not isinstance(key_data.get("duration"), str)
            or not isinstance(key_data.get("fix_mec_timezone"), bool)
        ):
            raise ValueError("Kalender-Cache-Schluessel ist ungueltig.")

        key = _build_calendar_item_key(key_data)
        if key in snapshot:
            raise ValueError("Kalender-Cache enthaelt doppelte Eintraege.")
        snapshot[key] = tuple(slides)

    return snapshot, refreshed_at
