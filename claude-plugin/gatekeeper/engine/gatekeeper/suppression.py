"""A suppression is absolute; approvals never override it."""
from .storage import suppression_id

KEYWORDS = ("STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT")


def is_stop(text, keywords=KEYWORDS):
    return isinstance(text, str) and text.strip().upper() in keywords


def check(db, recipient):
    if db.execute("SELECT 1 FROM suppressions WHERE recipient_id=?", (suppression_id(recipient),)).fetchone():
        return "block", "suppressed"
    return None
