from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import logging
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from icalendar import Calendar

logger = logging.getLogger(__name__)
DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")


def build_calendar_events(item: dict, now: datetime | None = None) -> list[dict]:
    ics_url = item.get("content")
    if not ics_url:
        return []

    return _build_events(item, now or _utc_now())


def _build_events(item: dict, now: datetime) -> list[dict]:
    ics_url = item.get("content")

    response = requests.get(ics_url, timeout=10)
    response.raise_for_status()
    calendar = Calendar.from_ical(response.text)
    if item.get("fix_mec_timezone", False):
        _apply_mec_timezone_fix(calendar)

    categories_filter = {value.strip() for value in item["categories"] if value}
    window_end = now + timedelta(days=item["days_ahead"])
    events = []

    for component in recurring_ical_events.of(calendar, skip_bad_series=True).between(now, window_end):
        start_value = component.get("dtstart")
        end_value = component.get("dtend")
        summary = str(component.get("summary", "")).strip() or "Ohne Titel"
        uid = _event_uid(component, ics_url, summary, None)
        if not start_value or not end_value:
            logger.warning(
                "Kalender-Event ohne gueltigen Zeitraum wird uebersprungen: "
                "uid=%s titel=%r",
                uid,
                summary,
            )
            continue

        try:
            start = _normalize_datetime(start_value.dt)
            end = _normalize_datetime(end_value.dt)
        except (AttributeError, TypeError, ValueError, OverflowError):
            logger.warning(
                "Kalender-Event mit ungueltigem Zeitraum wird uebersprungen: "
                "uid=%s titel=%r",
                uid,
                summary,
            )
            continue
        if end <= start:
            logger.warning(
                "Kalender-Event mit nicht positiver Dauer wird uebersprungen: "
                "uid=%s titel=%r",
                uid,
                summary,
            )
            continue

        categories = _normalize_categories(component.get("categories"))
        matching_categories = [category for category in categories if category in categories_filter]
        if categories_filter and not matching_categories:
            continue

        description = str(component.get("description", "")).strip()
        uid = _event_uid(component, ics_url, summary, start)
        event_url = _normalize_event_url(component.get("url"))
        events.append(
            {
                "uid": uid,
                "title": summary,
                "description": description,
                "categories": categories,
                "image_url": str(component.get("attach", "")).strip(),
                "event_url": event_url,
                "start": start,
                "end": end,
            }
        )

    events.sort(key=lambda entry: entry["start"])
    return _keep_next_event_per_uid(events)


def _keep_next_event_per_uid(events: list[dict]) -> list[dict]:
    next_events = []
    seen_uids = set()

    for event in events:
        uid = event["uid"]
        if uid in seen_uids:
            continue
        seen_uids.add(uid)
        next_events.append(event)

    return next_events


def _event_uid(
    component,
    ics_url: str,
    summary: str,
    start: datetime | None,
) -> str:
    uid = str(component.get("uid", "")).strip()
    if uid:
        return uid

    fallback_source = "\0".join(
        (ics_url, summary, start.isoformat() if start is not None else "")
    )
    return f"generated-{sha256(fallback_source.encode('utf-8')).hexdigest()}"


def _normalize_datetime(value) -> datetime:
    # ICS feeds may contain either full datetimes or date-only values.
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _apply_mec_timezone_fix(calendar: Calendar) -> None:
    # MEC adds the Berlin UTC offset to some local values. Correct the original
    # event before recurrence expansion so a winter series keeps its local time.
    for component in calendar.walk("VEVENT"):
        for property_name in ("DTSTART", "DTEND"):
            _correct_mec_datetime_property(component, property_name)

        for property_name in ("RDATE", "EXDATE"):
            _correct_mec_datetime_list_property(component, property_name)


def _correct_mec_datetime_property(component, property_name: str) -> None:
    property_value = component.get(property_name)
    if property_value is None or not _uses_berlin_timezone(property_value):
        return

    corrected_value = _subtract_timezone_offset(property_value.dt)
    parameters = dict(property_value.params)
    del component[property_name]
    component.add(property_name, corrected_value, parameters=parameters)


def _correct_mec_datetime_list_property(component, property_name: str) -> None:
    property_values = component.get(property_name)
    if property_values is None:
        return

    if not isinstance(property_values, list):
        property_values = [property_values]

    if not any(_uses_berlin_timezone(property_value) for property_value in property_values):
        return

    rebuilt_values = []
    for property_value in property_values:
        values = [value.dt for value in property_value.dts]
        if _uses_berlin_timezone(property_value):
            values = [_subtract_timezone_offset(value) for value in values]
        rebuilt_values.append((values, dict(property_value.params)))

    del component[property_name]
    for values, parameters in rebuilt_values:
        component.add(property_name, values, parameters=parameters)


def _uses_berlin_timezone(property_value) -> bool:
    return str(property_value.params.get("TZID", "")) == DISPLAY_TIMEZONE.key


def _subtract_timezone_offset(value):
    if isinstance(value, tuple):
        return tuple(_subtract_timezone_offset(part) for part in value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        return value
    return value - value.utcoffset()


def _normalize_categories(value) -> list[str]:
    if value is None:
        return []

    if hasattr(value, "cats"):
        raw_values = value.cats
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = [value]

    categories = []
    for raw_value in raw_values:
        text = str(raw_value)
        parts = [part.strip() for part in text.split(",")]
        categories.extend([part for part in parts if part])

    return categories


def _normalize_event_url(value) -> str:
    event_url = str(value or "").strip()
    parsed_url = urlparse(event_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        return ""
    return event_url
