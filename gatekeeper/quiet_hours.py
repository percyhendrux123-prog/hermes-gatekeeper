"""Owner-defined recipient-local permitted sending windows."""
from datetime import time
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def clock(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value):
        raise ValueError("use HH:MM")
    return time.fromisoformat(value)


def window(start, end):
    first, last = clock(start), clock(end)
    if first == last:
        raise ValueError("empty window")
    return first, last


def check(contact, now, start="08:00", end="21:00", overrides=None):
    zone = contact.get("timezone")
    if not zone:
        return "approve", "unknown_timezone"
    try:
        tz = ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        return "approve", "unknown_timezone"
    if now.tzinfo is None:
        raise ValueError("aware time required")
    first, last = window(*(overrides or {}).get(contact.get("region"), (start, end)))
    local = now.astimezone(tz).time()
    allowed = first <= local < last if first < last else local >= first or local < last
    return None if allowed else ("block", "quiet_hours")
