"""Explicit owner records; inbound replies never grant consent."""
from datetime import date as calendar_date
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .storage import recipient_id


def channel_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", value):
        raise ValueError("invalid channel")
    return value


def contact(db, recipient, channel):
    row = db.execute("SELECT * FROM contacts WHERE recipient_id=? AND channel=?",
                     (recipient_id(recipient), channel_id(channel))).fetchone()
    return dict(row) if row else {}


def record(db, recipient, channel, source, date, timezone="", region=""):
    channel = channel_id(channel)
    if not isinstance(source, str) or not source.strip() or len(source) > 512:
        raise ValueError("invalid consent source")
    if not isinstance(date, str) or calendar_date.fromisoformat(date).isoformat() != date:
        raise ValueError("invalid consent date")
    if not isinstance(timezone, str) or not isinstance(region, str) or len(region) > 64:
        raise ValueError("invalid location metadata")
    if timezone:
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("invalid timezone") from exc
    db.execute("INSERT INTO contacts (recipient_id,channel,source,date,timezone,region) VALUES (?,?,?,?,?,?) "
               "ON CONFLICT(recipient_id,channel) DO UPDATE SET source=excluded.source,date=excluded.date,"
               "timezone=excluded.timezone,region=excluded.region",
               (recipient_id(recipient), channel, source, date, timezone, region))


def revoke(db, recipient, channel):
    db.execute("UPDATE contacts SET source='',date='' WHERE recipient_id=? AND channel=?",
               (recipient_id(recipient), channel_id(channel)))


def check(db, recipient, channel, require=True):
    row = contact(db, recipient, channel)
    if require and not (row.get("source") and row.get("date")):
        return "block", "no_consent"
    return None
