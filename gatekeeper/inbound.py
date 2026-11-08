"""Observe only the public normalized, profile-scoped admission snapshot."""
import json
import logging

from . import consent, history, suppression
from .storage import body_hash, canonical_recipient

logger = logging.getLogger("hermes-gatekeeper")


def observe(service, *, platform="", source=None, message_id="", text="", **kwargs):
    stop = suppression.is_stop(text, service.settings.stop_keywords)
    try:
        if platform in {"cli", "tui", "desktop", "local", ""}:
            return None
        consent.channel_id(platform)
        if not isinstance(source, dict):
            raise ValueError("missing identity")
        sender, chat = source.get("user_id"), source.get("chat_id")
        dm = source.get("chat_type") == "dm"
        thread = source.get("thread_id") or ""
        if stop:
            targets = {canonical_recipient(r) for r in (sender, chat if dm else None) if r}
            if not targets:
                raise ValueError("missing STOP sender")
            with service.ledger.transaction() as db:
                for target in targets:
                    service.ledger.optout(db, target)
                    service.ledger.log(db, platform, target, "", text, "inbound_stop", "block", service.now().timestamp())
            return {"action": "handled"}  # do not emit an unsolicited confirmation
        if dm and chat:
            with service.ledger.transaction() as db:
                if message_id:
                    key = body_hash(json.dumps([platform, chat, thread, message_id], sort_keys=True))
                    if not db.execute("INSERT OR IGNORE INTO inbound_seen VALUES (?)", (key,)).rowcount:
                        return None
                history.reply(db, chat, platform, thread, at=service.now().timestamp())
    except Exception:
        # A missed STOP/reply must not leave outbound sends running as if storage were healthy.
        service.unhealthy.set()
        logger.warning("Gatekeeper inbound observation failed; repair records and reload before further sends.")
        if stop:
            return {"action": "handled"}
    return None
