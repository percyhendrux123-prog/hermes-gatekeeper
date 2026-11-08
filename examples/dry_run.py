"""Offline demonstration: real policy/SQLite, synthetic host observations, no sends."""
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from gatekeeper.config import Settings
from gatekeeper.service import Gatekeeper
from gatekeeper.storage import Ledger


def main():
    with TemporaryDirectory(prefix="gatekeeper-demo-") as directory:
        path = Path(directory) / "demo.db"
        gate = Gatekeeper(Settings.parse({"templates": ["Demo notice."]}),
                          Ledger(lambda: sqlite3.connect(path)),
                          now=lambda: datetime(2026, 1, 1, 16, tzinfo=timezone.utc))
        args = {"target": "sms:+1-555-0100", "message": "Demo notice."}

        def attempt(label, call_id, message="Demo notice."):
            call = {**args, "message": message}
            gate.before("send_message", call, tool_call_id=call_id)
            with gate.ledger.transaction() as db:
                row = db.execute("SELECT outcome,rule FROM decisions ORDER BY id DESC LIMIT 1").fetchone()
                print(f"{label}: {row['outcome']} ({row['rule']})")
            return call

        attempt("no consent", "one")
        gate.command("consent +1-555-0100 sms synthetic-form 2026-01-01 UTC", platform="cli")
        attempt("approved routine", "two")
        # Synthetic public-hook delivery observation; no transport is installed or invoked.
        gate.after("send_message", args, result='{"success":true}', status="ok", tool_call_id="two")
        attempt("unanswered thread", "three")
        gate.after("send_message", args, result="{}", status="cancelled", tool_call_id="three")
        identity = {"user_id": "+1-555-0100", "chat_id": "+1-555-0100", "chat_type": "dm", "thread_id": ""}
        gate.inbound(platform="sms", source=identity, message_id="demo-reply", text="Synthetic reply.")
        attempt("after observed reply", "four")
        gate.after("send_message", args, result="{}", status="cancelled", tool_call_id="four")
        attempt("changed wording", "five", "Changed demo wording.")
        gate.inbound(platform="sms", source=identity, message_id="demo-stop", text="STOP")
        attempt("after STOP", "six")
        with gate.ledger.transaction() as db:
            count = db.execute("SELECT count(*) FROM decisions").fetchone()[0]
        print(f"decisions logged: {count}; transports invoked: 0")


if __name__ == "__main__":
    main()
