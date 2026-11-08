"""Public hook policy orchestration. The host, never this plugin, sends."""
from datetime import datetime, timezone
import json
import logging
from threading import Event

from . import consent, double_text, history, quiet_hours, suppression, wording
from .classify import classify, Uninspectable
from .storage import body_hash

logger = logging.getLogger("hermes-gatekeeper")
RANK = {"pass": 0, "approve": 1, "block": 2}


def call_key(tool_name, args, context):
    return body_hash(json.dumps([tool_name, args, context.get("session_id", ""),
                                context.get("task_id", ""), context.get("tool_call_id", "")],
                               sort_keys=True, ensure_ascii=True, separators=(",", ":")))


def directive(outcome, rules, key=""):
    if outcome == "pass":
        return None
    result = {"action": outcome, "message": "Gatekeeper: " + ", ".join(sorted(set(rules))) +
              (". Send blocked." if outcome == "block" else ". Owner approval required through Hermes.")}
    if outcome == "approve":
        result["rule_key"] = "gatekeeper:" + key
    return result


class Gatekeeper:
    def __init__(self, settings, ledger, *, now=None, config_error=False):
        self.settings, self.ledger = settings, ledger
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.config_error = config_error
        self.unhealthy = Event()

    def evaluate(self, db, send, now):
        hard = (suppression.check(db, send.recipient) or
                consent.check(db, send.recipient, send.channel, self.settings.require_consent))
        if hard:
            return [hard]
        contact = consent.contact(db, send.recipient, send.channel)
        rules = [quiet_hours.check(contact, now, self.settings.start, self.settings.end, self.settings.region_windows),
                 double_text.check(db, send.recipient, send.channel, send.thread, now=now.timestamp(),
                                   min_gap=self.settings.min_gap_seconds),
                 wording.check(send.message, self.settings.templates, json.loads(contact.get("variables", "{}")))]
        return [r for r in rules if r] or [("pass", "routine")]

    def error(self, rule, tool_name, args):
        # Never serialize exception messages: they can include args, paths or bodies.
        try:
            with self.ledger.transaction() as db:
                self.ledger.log(db, "unresolved", "unresolved", "", json.dumps([tool_name, args], sort_keys=True),
                                rule, "block", self.now().timestamp())
        except Exception:
            logger.warning("Gatekeeper could not persist a blocked decision; send remains blocked.")
        return directive("block", [rule])

    def before(self, tool_name="", args=None, **kwargs):
        try:
            sends = classify(tool_name, args)
        except Uninspectable:
            return self.error("uninspectable", tool_name, args)
        except Exception:
            return self.error("gate_error", tool_name, args)
        if not sends:
            return None
        try:
            if self.config_error or self.unhealthy.is_set():
                return self.error("gate_unavailable", tool_name, args)
            now, key = self.now(), call_key(tool_name, args, kwargs)
            with self.ledger.transaction() as db:
                evaluations = [self.evaluate(db, send, now) for send in sends]
                outcome = max((r[0] for rules in evaluations for r in rules), key=RANK.get)
                for send, rules in zip(sends, evaluations):
                    rule = max(rules, key=lambda r: RANK[r[0]])[1]
                    decision = self.ledger.log(db, send.channel, send.recipient, send.thread, send.message,
                                               rule, outcome, now.timestamp())
                    # Deferred batches are checked again at each leaf; don't reserve twice.
                    if outcome != "block" and tool_name.rsplit(".", 1)[-1] in {"send_message", "terminal"}:
                        history.reserve(db, send.recipient, send.channel, send.thread, at=now.timestamp(),
                                        call_key=key, decision=decision)
            return directive(outcome, [r[1] for rules in evaluations for r in rules if r[0] != "pass"], key)
        except Exception:
            return self.error("gate_error", tool_name, args)

    def inbound(self, **kwargs):
        from .inbound import observe
        return observe(self, **kwargs)

    def command(self, raw="", **kwargs):
        from .commands import command
        return command(self, raw, **kwargs)

    def after(self, tool_name="", args=None, result="", status="", **kwargs):
        try:
            sends = classify(tool_name, args)
            if not sends or tool_name.rsplit(".", 1)[-1] not in {"send_message", "terminal"}:
                return None
            state = "failed" if status in {"blocked", "cancelled"} else None
            data = json.loads(result) if isinstance(result, str) else result
            if status == "ok" and isinstance(data, dict):
                if tool_name.rsplit(".", 1)[-1] == "send_message":
                    if data.get("success") is True and not data.get("skipped"):
                        state = "sent"
                elif type(data.get("exit_code")) is int and data["exit_code"] == 0:
                    state = "sent"
            if state and isinstance(kwargs.get("tool_call_id"), str) and kwargs["tool_call_id"]:
                with self.ledger.transaction() as db:
                    history.finish(db, call_key(tool_name, args, kwargs), state, at=self.now().timestamp())
        except Uninspectable:
            if status != "blocked":
                self.unhealthy.set()
                logger.warning("Gatekeeper observed an uninspectable send outcome; further sends are blocked.")
        except Exception:
            self.unhealthy.set()
            logger.warning("Gatekeeper send observation failed; further sends are blocked until owner repair and reload.")
        return None
