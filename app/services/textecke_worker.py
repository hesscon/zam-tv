import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests

from .calendar_service import build_calendar_events
from .config_service import load_config


logger = logging.getLogger(__name__)
DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")
WEEKDAYS = ("MO", "DI", "MI", "DO", "FR", "SA", "SO")
DEFAULT_TEXT = "Entdecke das ZAM in dir"
MAX_MESSAGE_BYTES = 200
SEARCH_DAYS = 7
HTTP_TIMEOUT_SECONDS = 10
DEFAULT_REFRESH_INTERVAL = timedelta(minutes=15)
DEFAULT_RETRY_INTERVAL = timedelta(minutes=5)

EventLoader = Callable[[dict, datetime | None], list[dict]]
HttpPost = Callable[..., object]
NowProvider = Callable[[], datetime]


class TexteckeWorker:
    def __init__(
        self,
        config_path: Path,
        *,
        refresh_interval: timedelta = DEFAULT_REFRESH_INTERVAL,
        retry_interval: timedelta = DEFAULT_RETRY_INTERVAL,
        event_loader: EventLoader = build_calendar_events,
        http_post: HttpPost = requests.post,
        now_provider: NowProvider | None = None,
    ) -> None:
        self._config_path = config_path
        self._refresh_interval = refresh_interval
        self._retry_interval = retry_interval
        self._event_loader = event_loader
        self._http_post = http_post
        self._now_provider = now_provider or _utc_now

        self._events: tuple[dict, ...] = ()
        self._textecke_config: dict | None = None
        self._config_identity: tuple | None = None
        self._has_successful_load = False
        self._last_sent_text: str | None = None
        self._post_retry_at: datetime | None = None
        self._post_retry_text: str | None = None

        self._thread_lock = Lock()
        self._stop_event = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        with self._thread_lock:
            if self._thread and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = Thread(
                target=self._run,
                name="textecke-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout)

    def refresh(self, now: datetime | None = None) -> bool:
        current_time = now or self._now_provider()
        succeeded = self._load_events(current_time)
        if self._has_successful_load:
            self._sync_message(current_time)
        return succeeded

    def _run(self) -> None:
        next_refresh_at = self._now_provider()
        transition: tuple[datetime, str] | None = None

        while not self._stop_event.is_set():
            now = self._now_provider()
            next_refresh_at, transition = self._process_due_actions(
                now,
                next_refresh_at,
                transition,
            )
            wake_at = next_refresh_at
            if transition is not None:
                wake_at = min(wake_at, transition[0])
            if self._post_retry_at is not None:
                wake_at = min(wake_at, self._post_retry_at)

            wait_seconds = max(0.0, (wake_at - now).total_seconds())
            self._stop_event.wait(wait_seconds)

    def _process_due_actions(
        self,
        now: datetime,
        next_refresh_at: datetime,
        transition: tuple[datetime, str] | None,
    ) -> tuple[datetime, tuple[datetime, str] | None]:
        refresh_for_event_end = (
            transition is not None
            and transition[1] == "end"
            and transition[0] <= now
        )
        if now >= next_refresh_at or refresh_for_event_end:
            succeeded = self._load_events(now)
            interval = self._refresh_interval if succeeded else self._retry_interval
            next_refresh_at = now + interval

        if self._has_successful_load:
            self._sync_message(now)

        return next_refresh_at, self._next_transition(now)

    def _load_events(self, now: datetime) -> bool:
        try:
            config = load_config(self._config_path)
            textecke = config.get("textecke")
            if not textecke or not textecke["enabled"]:
                self._disable()
                return True

            source_config = {
                "content": textecke["content"],
                "categories": textecke["categories"],
                "days_ahead": SEARCH_DAYS,
                "fix_mec_timezone": textecke["fix_mec_timezone"],
            }
            events = self._event_loader(source_config, now)
        except Exception as exc:
            logger.error(
                "Textecke-Kalender konnte nicht aktualisiert werden: "
                "fehler=%s. Naechster Versuch in %.0fs.",
                _safe_error_message(exc),
                self._retry_interval.total_seconds(),
            )
            return False

        identity = (
            textecke["content"],
            tuple(textecke["categories"]),
            textecke["fix_mec_timezone"],
            textecke["message_url"],
        )
        if identity != self._config_identity:
            self._last_sent_text = None
            self._clear_post_retry()

        self._textecke_config = textecke
        self._config_identity = identity
        self._events = tuple(events)
        self._has_successful_load = True
        logger.info(
            "Textecke-Kalender aktualisiert: quelle=%s events=%d",
            _display_source(textecke["content"]),
            len(events),
        )
        return True

    def _disable(self) -> None:
        if self._textecke_config is not None:
            logger.info("Textecke ist deaktiviert.")
        self._events = ()
        self._textecke_config = None
        self._config_identity = None
        self._has_successful_load = False
        self._last_sent_text = None
        self._clear_post_retry()

    def _sync_message(self, now: datetime) -> bool:
        if self._textecke_config is None:
            return True

        event = select_current_or_next_event(self._events, now)
        desired_text = build_message(event, now)
        if desired_text == self._last_sent_text:
            self._clear_post_retry()
            return True

        if self._post_retry_text != desired_text:
            self._clear_post_retry()
        if self._post_retry_at is not None and now < self._post_retry_at:
            return False

        try:
            response = self._http_post(
                self._textecke_config["message_url"],
                json={"text": desired_text},
                timeout=HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except Exception as exc:
            self._post_retry_text = desired_text
            self._post_retry_at = now + self._retry_interval
            logger.error(
                "Textecke-Nachricht konnte nicht gesendet werden: "
                "fehler=%s. Naechster Versuch in %.0fs.",
                _safe_error_message(exc),
                self._retry_interval.total_seconds(),
            )
            return False

        self._last_sent_text = desired_text
        self._clear_post_retry()
        logger.info(
            "Textecke-Nachricht aktualisiert: bytes=%d",
            len(desired_text.encode("utf-8")),
        )
        return True

    def _next_transition(self, now: datetime) -> tuple[datetime, str] | None:
        if not self._has_successful_load:
            return None
        event = select_current_or_next_event(self._events, now)
        if event is None:
            return None
        if event["start"] > now:
            return event["start"], "start"
        return event["end"], "end"

    def _clear_post_retry(self) -> None:
        self._post_retry_at = None
        self._post_retry_text = None


def select_current_or_next_event(
    events: tuple[dict, ...] | list[dict],
    now: datetime,
) -> dict | None:
    for event in events:
        if event["start"] <= now < event["end"]:
            return event
    for event in events:
        if event["start"] > now:
            return event
    return None


def build_message(event: dict | None, now: datetime) -> str:
    if event is None:
        return DEFAULT_TEXT

    if event["start"] <= now < event["end"]:
        prefix = "JETZT · "
    else:
        local_start = event["start"].astimezone(DISPLAY_TIMEZONE)
        prefix = (
            f"{WEEKDAYS[local_start.weekday()]} "
            f"{local_start.strftime('%H:%M')} · "
        )
    return _fit_title(prefix, event["title"])


def _fit_title(prefix: str, title: str) -> str:
    normalized_title = " ".join(title.split())
    available_bytes = MAX_MESSAGE_BYTES - len(prefix.encode("utf-8"))
    words = []

    for word in normalized_title.split(" "):
        candidate = " ".join((*words, word))
        if len(candidate.encode("utf-8")) > available_bytes:
            break
        words.append(word)

    if not words:
        return prefix.rstrip()
    return prefix + " ".join(words)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _display_source(source: str) -> str:
    parts = urlsplit(source)
    if parts.scheme and parts.netloc:
        value = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    else:
        value = source.split("?", 1)[0].split("#", 1)[0]
    return f"{value[:197]}..." if len(value) > 200 else value


def _safe_error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split()) or exc.__class__.__name__
    message = re.sub(
        r"(https?://[^\s?#]+(?:/[^\s?#]*)?)\?[^\s#]*",
        r"\1?[ausgeblendet]",
        message,
    )
    return f"{message[:497]}..." if len(message) > 500 else message
