"""Local-human administration only; never registered as an agent tool."""
from datetime import datetime, timezone
import json
import shlex

from . import consent, history
from .storage import recipient_id
from .wording import validate_variables

USAGE = ("Usage: /gatekeeper [log [1-50] | optout <recipient> | "
         "consent <recipient> <channel> <source> <YYYY-MM-DD> <timezone|unknown> [region] | "
         "revoke <recipient> <channel> | reply <recipient> <channel> [thread] | "
         "variables <recipient> <channel> '<JSON object>']")


def command(service, raw="", *, platform="", source=None, **kwargs):
    # Public calling-session keywords; same local-owner boundary as Standing.
    if platform not in {"cli", "tui", "desktop", "local"} or source is not None:
        return "Only the local owner at a Hermes terminal or desktop can use Gatekeeper commands."
    try:
        parts = shlex.split(raw)
        with service.ledger.transaction() as db:
            if not parts:
                counts = {table: db.execute("SELECT count(*) FROM " + table).fetchone()[0]
                          for table in ("suppressions", "contacts", "decisions")}
                state = "needs attention" if service.config_error or service.unhealthy.is_set() else "ready"
                return (f"Gatekeeper: {state}; suppressed: {counts['suppressions']}; "
                        f"contacts: {counts['contacts']}; decisions: {counts['decisions']}. "
                        "Only hook-visible sends are gated. " + USAGE)
            name, args = parts[0], parts[1:]
            if name == "log" and len(args) <= 1:
                count = int(args[0]) if args else 10
                if not 1 <= count <= 50:
                    raise ValueError("invalid limit")
                rows = db.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT ?", (count,)).fetchall()
                return "\n".join(f"{datetime.fromtimestamp(r['at'], timezone.utc).isoformat()} | {r['channel']} | "
                                 f"{r['recipient_id'][:12]} | {r['rule']} | {r['outcome']}" for r in rows) or "No decisions yet."
            if name == "optout" and len(args) == 1:
                service.ledger.optout(db, args[0])
                return "Gatekeeper: recipient suppressed. Approval and new consent cannot override suppression."
            if name == "consent" and len(args) in {5, 6}:
                recipient, channel, origin, date, zone, *region = args
                consent.record(db, recipient, channel, origin, date, "" if zone == "unknown" else zone, region[0] if region else "")
                return "Gatekeeper: channel consent recorded; suppression still applies."
            if name == "revoke" and len(args) == 2:
                consent.revoke(db, *args)
                return "Gatekeeper: channel consent revoked."
            if name == "reply" and len(args) in {2, 3}:
                history.reply(db, args[0], args[1], args[2] if len(args) == 3 else "", at=service.now().timestamp(), owner=True)
                return "Gatekeeper: owner-observed reply recorded. No consent was granted."
            if name == "variables" and len(args) == 3:
                recipient, channel, raw_values = args
                values = validate_variables(json.loads(raw_values))
                if not consent.contact(db, recipient, channel):
                    raise ValueError("record contact first")
                db.execute("UPDATE contacts SET variables=? WHERE recipient_id=? AND channel=?",
                           (json.dumps(values, sort_keys=True), recipient_id(recipient), channel))
                return "Gatekeeper: owner template variables saved."
        return USAGE
    except (ValueError, TypeError):
        return USAGE
    except Exception:
        return "Gatekeeper could not read or change its record. Check local storage and settings."
