from base64 import b64encode
import json
import logging
from datetime import datetime
from hashlib import sha256
from typing import Callable
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg

from .calendar_service import build_calendar_events
from .caption_worker_client import CaptionWorkerClient
from .event_caption_worker import MAX_DESCRIPTION_CHARS, normalize_source_text


logger = logging.getLogger(__name__)
GERMAN_WEEKDAY_NAMES = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]
GERMAN_MONTH_NAMES = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]
DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")
CalendarItemKey = tuple[str, tuple[str, ...], int, str, bool]
CalendarSnapshot = dict[CalendarItemKey, tuple[dict, ...]]
SnapshotProgressCallback = Callable[[CalendarSnapshot], None]


class CalendarSnapshotBuilder:
    def __init__(self, caption_worker: CaptionWorkerClient | None) -> None:
        self._caption_worker = caption_worker

    def build(
        self,
        config: dict,
        previous_snapshot: CalendarSnapshot,
        on_progress: SnapshotProgressCallback | None = None,
    ) -> CalendarSnapshot:
        previous_captions = _index_previous_captions(previous_snapshot)
        slide_lists: dict[CalendarItemKey, list[dict]] = {}
        worker_requests: dict[str, dict] = {}
        worker_targets: dict[str, list[tuple[dict, str]]] = {}
        worker_context: dict[str, tuple[str, str]] = {}
        event_count = 0
        reused_count = 0
        without_description_count = 0
        caption_generation_enabled = False

        for item in config.get("items", []):
            if not item.get("enabled", True) or item.get("type") != "calendar":
                continue

            key = build_calendar_item_key(item)
            if key in slide_lists:
                continue
            if item.get("caption_generation_enabled", False):
                caption_generation_enabled = True

            slides = []
            events = build_calendar_events(item)
            logger.info(
                "ICS-Abruf erfolgreich: quelle=%s events=%d",
                _display_calendar_source(item.get("content", "")),
                len(events),
            )
            for event in events:
                event_count += 1
                uid = event["uid"]
                title = normalize_source_text(event["title"])
                description = normalize_source_text(event["description"])[
                    :MAX_DESCRIPTION_CHARS
                ]
                input_hash = _caption_input_hash(title, description)
                identity = (key[0], uid, input_hash)
                slide = {
                    **_build_calendar_slide(item, event),
                    "uid": uid,
                    "caption": "",
                }

                if identity in previous_captions:
                    slide["caption_input_hash"] = input_hash
                    slide["caption"] = previous_captions[identity]
                    reused_count += 1
                elif not description:
                    slide["caption_input_hash"] = input_hash
                    without_description_count += 1
                elif item.get("caption_generation_enabled", False):
                    request_id = _worker_request_id(*identity)
                    worker_requests.setdefault(
                        request_id,
                        {
                            "uid": request_id,
                            "title": title,
                            "description": description,
                        },
                    )
                    worker_targets.setdefault(request_id, []).append(
                        (slide, input_hash)
                    )
                    worker_context.setdefault(request_id, (uid, title))

                slides.append(slide)

            slide_lists[key] = slides

        snapshot = {
            key: tuple(slides)
            for key, slides in slide_lists.items()
        }
        if caption_generation_enabled:
            logger.info(
                "Caption-Verarbeitung gestartet: angefragt=%d "
                "wiederverwendet=%d ohne_beschreibung=%d",
                len(worker_requests),
                reused_count,
                without_description_count,
            )
        error_count = self._apply_generated_captions(
            worker_requests,
            worker_targets,
            worker_context,
            snapshot,
            on_progress,
        )
        if caption_generation_enabled:
            logger.info(
                "Caption-Verarbeitung abgeschlossen: angefragt=%d "
                "wiederverwendet=%d fehler=%d",
                len(worker_requests),
                reused_count,
                error_count,
            )
        return snapshot

    def _apply_generated_captions(
        self,
        worker_requests: dict[str, dict],
        worker_targets: dict[str, list[tuple[dict, str]]],
        worker_context: dict[str, tuple[str, str]],
        snapshot: CalendarSnapshot,
        on_progress: SnapshotProgressCallback | None,
    ) -> int:
        if not worker_requests:
            return 0
        if self._caption_worker is None:
            logger.error(
                "Caption-Worker ist nicht konfiguriert: events=%d",
                len(worker_requests),
            )
            for targets in worker_targets.values():
                _mark_targets_complete(targets, "")
            if on_progress is not None:
                on_progress(snapshot)
            return len(worker_requests)

        error_count = 0
        completed_ids: set[str] = set()
        try:
            results = iter(
                self._caption_worker.generate(list(worker_requests.values()))
            )
        except Exception as exc:
            return self._handle_worker_failure(
                exc,
                worker_targets,
                worker_context,
                completed_ids,
                snapshot,
                on_progress,
                error_count,
            )

        while True:
            try:
                result = next(results)
            except StopIteration:
                break
            except Exception as exc:
                return self._handle_worker_failure(
                    exc,
                    worker_targets,
                    worker_context,
                    completed_ids,
                    snapshot,
                    on_progress,
                    error_count,
                )

            request_id = result.get("uid")
            if not isinstance(request_id, str) or request_id not in worker_targets:
                logger.error("Unerwartetes Caption-Ergebnis: %r", request_id)
                error_count += 1
                continue
            if request_id in completed_ids:
                logger.error("Doppeltes Caption-Ergebnis: %s", request_id)
                error_count += 1
                continue

            completed_ids.add(request_id)
            error_count += self._apply_result(
                request_id,
                result,
                worker_targets,
                worker_context,
            )
            if on_progress is not None:
                on_progress(snapshot)

        missing_ids = worker_targets.keys() - completed_ids
        for request_id in missing_ids:
            uid, title = worker_context[request_id]
            logger.error(
                "Caption-Ergebnis fehlt: uid=%s titel=%r",
                uid,
                title,
            )
            _mark_targets_complete(worker_targets[request_id], "")
            error_count += 1

        if missing_ids and on_progress is not None:
            on_progress(snapshot)
        return error_count

    def _handle_worker_failure(
        self,
        exc: Exception,
        worker_targets: dict[str, list[tuple[dict, str]]],
        worker_context: dict[str, tuple[str, str]],
        completed_ids: set[str],
        snapshot: CalendarSnapshot,
        on_progress: SnapshotProgressCallback | None,
        error_count: int,
    ) -> int:
        logger.exception(
            "Caption-Worker fehlgeschlagen: events=%d erledigt=%d",
            len(worker_targets),
            len(completed_ids),
        )
        remaining_ids = worker_targets.keys() - completed_ids
        for request_id in remaining_ids:
            uid, title = worker_context[request_id]
            logger.error(
                "Caption-Erzeugung fehlgeschlagen: uid=%s titel=%r fehler=%s",
                uid,
                title,
                exc,
            )
            _mark_targets_complete(worker_targets[request_id], "")
        if remaining_ids and on_progress is not None:
            on_progress(snapshot)
        return error_count + len(remaining_ids)

    def _apply_result(
        self,
        request_id: str,
        result: dict,
        worker_targets: dict[str, list[tuple[dict, str]]],
        worker_context: dict[str, tuple[str, str]],
    ) -> int:
        uid, title = worker_context[request_id]
        caption = result.get("caption")

        if result.get("error"):
            logger.error(
                "Caption-Erzeugung fehlgeschlagen: uid=%s titel=%r fehler=%s",
                uid,
                title,
                result["error"],
            )
            _mark_targets_complete(worker_targets[request_id], "")
            return 1

        if not isinstance(caption, str):
            logger.error(
                "Caption-Ergebnis ist ungueltig: uid=%s titel=%r",
                uid,
                title,
            )
            _mark_targets_complete(worker_targets[request_id], "")
            return 1

        _mark_targets_complete(worker_targets[request_id], caption)
        if caption:
            logger.info(
                "Caption erzeugt: uid=%s titel=%r",
                uid,
                title,
            )
        else:
            logger.info(
                "Keine Caption erforderlich: uid=%s titel=%r",
                uid,
                title,
            )
        return 0


def _build_calendar_slide(item: dict, event: dict) -> dict:
    configured_categories = {
        value.strip() for value in item.get("categories", []) if value
    }
    matching_categories = [
        category
        for category in event["categories"]
        if category in configured_categories
    ]
    category = (
        matching_categories[0]
        if matching_categories
        else (event["categories"][0] if event["categories"] else "")
    )
    return {
        "type": "calendar_event",
        "duration": item.get("duration", 15),
        "category": category,
        "summary": event["title"],
        "image_url": event["image_url"],
        "event_url": event["event_url"],
        "qr_code_data_uri": _build_qr_code_data_uri(event["event_url"]),
        "start_iso": event["start"].isoformat(),
        "start_label": _format_start_label(event["start"]),
    }


def _format_start_label(value: datetime) -> str:
    local_value = value.astimezone(DISPLAY_TIMEZONE)
    weekday = GERMAN_WEEKDAY_NAMES[local_value.weekday()]
    month = GERMAN_MONTH_NAMES[local_value.month - 1]
    return (
        f"{weekday}, {local_value.day}. {month} "
        f"{local_value.strftime('%H:%M')}"
    )


def _build_qr_code_data_uri(event_url: str) -> str:
    if not event_url:
        return ""

    try:
        qr_code = qrcode.make(
            event_url,
            image_factory=qrcode.image.svg.SvgPathFillImage,
        )
    except (qrcode.exceptions.DataOverflowError, ValueError):
        return ""

    encoded_svg = b64encode(qr_code.to_string()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_svg}"


def _mark_targets_complete(
    targets: list[tuple[dict, str]],
    caption: str,
) -> None:
    for slide, input_hash in targets:
        slide["caption_input_hash"] = input_hash
        slide["caption"] = caption


def build_calendar_item_key(item: dict) -> CalendarItemKey:
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


def _index_previous_captions(
    snapshot: CalendarSnapshot,
) -> dict[tuple[str, str, str], str]:
    captions = {}
    for key, slides in snapshot.items():
        for slide in slides:
            uid = slide.get("uid")
            input_hash = slide.get("caption_input_hash")
            caption = slide.get("caption")
            if (
                isinstance(uid, str)
                and isinstance(input_hash, str)
                and isinstance(caption, str)
            ):
                captions.setdefault((key[0], uid, input_hash), caption)
    return captions


def _caption_input_hash(title: str, description: str) -> str:
    payload = json.dumps(
        {"title": title, "description": description},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _display_calendar_source(source: str) -> str:
    parts = urlsplit(source)
    if parts.scheme and parts.netloc:
        display_value = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    else:
        display_value = source.split("?", 1)[0].split("#", 1)[0]
    if len(display_value) > 200:
        return f"{display_value[:197]}..."
    return display_value


def _worker_request_id(source: str, uid: str, input_hash: str) -> str:
    value = "\0".join((source, uid, input_hash))
    return sha256(value.encode("utf-8")).hexdigest()
