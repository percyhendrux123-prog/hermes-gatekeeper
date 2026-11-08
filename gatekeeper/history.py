"""Conservative thread history: pending sends count until proven cancelled."""
from .consent import channel_id
from .storage import recipient_id, thread_id


def key(recipient, channel, thread):
    return recipient_id(recipient), channel_id(channel), thread_id(thread)


def reserve(db, recipient, channel, thread, *, at, call_key, decision):
    db.execute("INSERT INTO messages (recipient_id,channel,thread_id,at,direction,state,call_key,decision) "
               "VALUES (?,?,?,?,'ours','pending',?,?)", (*key(recipient, channel, thread), at, call_key, decision))


def reply(db, recipient, channel, thread, *, at):
    db.execute("INSERT INTO messages (recipient_id,channel,thread_id,at,direction,state) "
               "VALUES (?,?,?,?,'reply','received')", (*key(recipient, channel, thread), at))


def finish(db, call_key, state):
    if state not in {"sent", "failed"}:
        raise ValueError("invalid state")
    db.execute("UPDATE messages SET state=? WHERE state='pending' AND id=(SELECT id FROM messages WHERE call_key=? "
               "ORDER BY id DESC LIMIT 1)", (state, call_key))
