from datetime import datetime, time, timezone

import requests
from icalendar import Calendar


def build_calendar_entries(item: dict) -> list[dict]:
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

    include_titles = {title.strip() for title in item.get("include_titles", []) if title}
    now = datetime.now(timezone.utc)
    events = []

    for component in calendar.walk("VEVENT"):
        summary = str(component.get("summary", "")).strip()
        start_value = component.get("dtstart")
        if not start_value:
            continue

        start = _normalize_datetime(start_value.dt)
        if start < now:
            continue

        if include_titles and summary not in include_titles:
            continue

        events.append(
            {
                "title": summary or "Ohne Titel",
                "start_iso": start.isoformat(),
                "start_label": start.astimezone().strftime("%d.%m.%Y %H:%M"),
            }
        )

    events.sort(key=lambda entry: entry["start_iso"])
    return events[: item.get("max_events", 5)]


def _normalize_datetime(value) -> datetime:
    # ICS feeds may contain either full datetimes or date-only values.
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    return datetime.combine(value, time.min, tzinfo=timezone.utc)
