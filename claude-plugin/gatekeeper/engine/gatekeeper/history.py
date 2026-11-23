"""Conservative thread history: pending sends count until proven cancelled."""
from .consent import channel_id
from .storage import recipient_id, thread_id


def key(recipient, channel, thread):
    return recipient_id(recipient), channel_id(channel), thread_id(thread)


def reserve(db, recipient, channel, thread, *, at, call_key, decision):
    db.execute("INSERT INTO messages (recipient_id,channel,thread_id,at,direction,state,call_key,decision) "
               "VALUES (?,?,?,?,'ours','pending',?,?)", (*key(recipient, channel, thread), at, call_key, decision))


def reply(db, recipient, channel, thread, *, at, owner=False):
    if owner:
        # The local owner explicitly attests an observed reply, including for
        # sends whose post-tool observation was unavailable.
        db.execute("UPDATE messages SET state='sent' WHERE recipient_id=? AND channel=? AND thread_id=? "
                   "AND state='pending'", key(recipient, channel, thread))
    db.execute("INSERT INTO messages (recipient_id,channel,thread_id,at,direction,state) "
               "VALUES (?,?,?,?,'reply','received')", (*key(recipient, channel, thread), at))


def finish(db, call_key, state, at=None):
    if state not in {"sent", "failed"}:
        raise ValueError("invalid state")
    row = db.execute("SELECT id,at,state FROM messages WHERE call_key=? ORDER BY id DESC LIMIT 1", (call_key,)).fetchone()
    if not row or row["state"] != "pending":
        return
    if state == "sent":
        # Completion is a conservative outbound ordering boundary. A reply that
        # arrived while approval/delivery was pending cannot clear this send.
        db.execute("UPDATE messages SET state='sent',at=?,id=(SELECT max(id)+1 FROM messages) WHERE id=?",
                   (row["at"] if at is None else at, row["id"]))
    else:
        db.execute("UPDATE messages SET state='failed' WHERE id=?", (row["id"],))
