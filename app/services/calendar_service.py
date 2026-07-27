from base64 import b64encode
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg
import recurring_ical_events
import requests
from icalendar import Calendar

GERMAN_WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
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
CACHE_TTL = timedelta(minutes=15)
DISPLAY_TIMEZONE = ZoneInfo("Europe/Berlin")
_slides_cache: dict[tuple[str, tuple[str, ...], int, str, bool], dict] = {}


def build_calendar_slides(item: dict) -> list[dict]:
    ics_url = item.get("content")
    if not ics_url:
        return []

    cache_key = _build_cache_key(item)
    now = _utc_now()
    cache_entry = _slides_cache.get(cache_key)
    if cache_entry and cache_entry["expires_at"] > now:
        return cache_entry["slides"]

    try:
        slides = _build_uncached_slides(item, now)
    except Exception:
        if cache_entry:
            return cache_entry["slides"]
        return []

    _slides_cache[cache_key] = {
        "slides": slides,
        "expires_at": now + CACHE_TTL,
    }
    return slides


def _build_cache_key(item: dict) -> tuple[str, tuple[str, ...], int, str, bool]:
    categories = tuple(sorted({value.strip() for value in item["categories"] if value}))
    return (
        item["content"],
        categories,
        item["days_ahead"],
        str(item["duration"]),
        item.get("fix_mec_timezone", False),
    )


def _build_uncached_slides(item: dict, now: datetime) -> list[dict]:
    ics_url = item.get("content")

    # Calendar fetch errors should not break the whole signage screen.
    response = requests.get(ics_url, timeout=10)
    response.raise_for_status()
    calendar = Calendar.from_ical(response.text)
    if item.get("fix_mec_timezone", False):
        _apply_mec_timezone_fix(calendar)

    categories_filter = {value.strip() for value in item["categories"] if value}
    window_end = now + timedelta(days=item["days_ahead"])
    slides = []

    for component in recurring_ical_events.of(calendar, skip_bad_series=True).between(now, window_end):
        start_value = component.get("dtstart")
        if not start_value:
            continue

        start = _normalize_datetime(start_value.dt)

        categories = _normalize_categories(component.get("categories"))
        matching_categories = [category for category in categories if category in categories_filter]
        if categories_filter and not matching_categories:
            continue

        event_url = _normalize_event_url(component.get("url"))
        slides.append(
            {
                "type": "calendar_event",
                "duration": item.get("duration", 15),
                "category": matching_categories[0] if matching_categories else (categories[0] if categories else ""),
                "summary": str(component.get("summary", "")).strip() or "Ohne Titel",
                "image_url": str(component.get("attach", "")).strip(),
                "event_url": event_url,
                "qr_code_data_uri": _build_qr_code_data_uri(event_url),
                "start_iso": start.isoformat(),
                "start_label": _format_start_label(start),
            }
        )

    slides.sort(key=lambda entry: entry["start_iso"])
    return slides


def _normalize_datetime(value) -> datetime:
    # ICS feeds may contain either full datetimes or date-only values.
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_start_label(value: datetime) -> str:
    local_value = value.astimezone(DISPLAY_TIMEZONE)
    weekday = GERMAN_WEEKDAY_NAMES[local_value.weekday()]
    month = GERMAN_MONTH_NAMES[local_value.month - 1]
    return f"{weekday}, {local_value.day}. {month} {local_value.strftime('%H:%M')}"


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


def _build_qr_code_data_uri(event_url: str) -> str:
    if not event_url:
        return ""

    try:
        qr_code = qrcode.make(event_url, image_factory=qrcode.image.svg.SvgPathFillImage)
    except (qrcode.exceptions.DataOverflowError, ValueError):
        return ""

    encoded_svg = b64encode(qr_code.to_string()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded_svg}"
