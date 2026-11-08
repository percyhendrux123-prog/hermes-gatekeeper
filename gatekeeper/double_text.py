"""Unanswered messages always hold; a configured gap also holds after replies."""
from .history import key


def check(db, recipient, channel, thread, *, now, min_gap=0):
    identity = key(recipient, channel, thread)
    last = db.execute("SELECT direction FROM messages WHERE recipient_id=? AND channel=? AND thread_id=? "
                      "AND state!='failed' ORDER BY id DESC LIMIT 1", identity).fetchone()
    if last and last["direction"] == "ours":
        return "approve", "unanswered"
    ours = db.execute("SELECT at FROM messages WHERE recipient_id=? AND channel=? AND thread_id=? "
                      "AND direction='ours' AND state!='failed' ORDER BY id DESC LIMIT 1", identity).fetchone()
    if ours and now - ours["at"] < min_gap:
        return "approve", "minimum_gap"
    return None
