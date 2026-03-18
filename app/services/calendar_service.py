from datetime import datetime, time, timedelta, timezone

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


def build_calendar_slides(item: dict) -> list[dict]:
    ics_url = item.get("content")
    if not ics_url:
        return []

    try:
        # Calendar fetch errors should not break the whole signage screen.
        response = requests.get(ics_url, timeout=10)
        response.raise_for_status()
        calendar = Calendar.from_ical(response.text)
    except Exception:
        return []

    categories_filter = {value.strip() for value in item.get("categories", []) if value}
    now = _utc_now()
    window_end = now + timedelta(days=int(item.get("days_ahead", 14)))
    slides = []

    for component in calendar.walk("VEVENT"):
        start_value = component.get("dtstart")
        if not start_value:
            continue

        start = _normalize_datetime(start_value.dt)
        if start < now or start > window_end:
            continue

        categories = _normalize_categories(component.get("categories"))
        matching_categories = [category for category in categories if category in categories_filter]
        if categories_filter and not matching_categories:
            continue

        slides.append(
            {
                "type": "calendar_event",
                "duration": item.get("duration", 15),
                "category": matching_categories[0] if matching_categories else (categories[0] if categories else ""),
                "summary": str(component.get("summary", "")).strip() or "Ohne Titel",
                "image_url": str(component.get("attach", "")).strip(),
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
    local_value = value.astimezone()
    weekday = GERMAN_WEEKDAY_NAMES[local_value.weekday()]
    month = GERMAN_MONTH_NAMES[local_value.month - 1]
    return f"{weekday}, {local_value.day}. {month} {local_value.strftime('%H:%M')}"


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
