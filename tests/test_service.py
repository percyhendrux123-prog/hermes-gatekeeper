import json
import sqlite3
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest


@pytest.fixture
def service(tmp_path):
    from gatekeeper.config import Settings
    from gatekeeper.storage import Ledger
    from gatekeeper.service import Gatekeeper
    ledger = Ledger(lambda: sqlite3.connect(tmp_path / "state.db", timeout=10))
    return Gatekeeper(Settings.parse({"templates": ["Demo notice."]}), ledger,
                      now=lambda: datetime(2026, 1, 1, 16, tzinfo=timezone.utc))


def seed(service, recipient="+1-555-0100", channel="sms", zone="UTC"):
    from gatekeeper.consent import record
    with service.ledger.transaction() as db:
        record(db, recipient, channel, "synthetic-form", "2026-01-01", zone)


def payload(recipient="+1-555-0100", message="Demo notice."):
    return {"target": "sms:" + recipient, "message": message}


def test_gate_real_ledger_routine_send_then_unanswered_hold(service):
    args = payload()
    assert service.before("send_message", args)["action"] == "block"
    seed(service)
    assert service.before("send_message", args, tool_call_id="one") is None
    service.after("send_message", args, result=json.dumps({"success": True}), status="ok", tool_call_id="one")
    decision = service.before("send_message", args, tool_call_id="two")
    assert decision["action"] == "approve" and "unanswered" in decision["message"]
    with service.ledger.transaction() as db:
        rows = [dict(r) for r in db.execute("select * from decisions order by id")]
        assert [r["outcome"] for r in rows] == ["block", "pass", "approve"]
        assert [r["rule"] for r in rows] == ["no_consent", "routine", "unanswered"]
        assert db.execute("select state from messages order by id").fetchone()[0] == "sent"


def test_suppression_outranks_wording_and_unknown_timezone(service):
    seed(service, zone="")
    with service.ledger.transaction() as db:
        service.ledger.optout(db, "+1-555-0100")
    result = service.before("send_message", payload(message="unapproved synthetic"))
    assert result["action"] == "block" and "suppressed" in result["message"]


def test_unknown_zone_and_unapproved_wording_hold(service):
    seed(service, zone="")
    result = service.before("send_message", payload(message="unapproved synthetic"))
    assert result["action"] == "approve" and "unknown_timezone" in result["message"]
    assert "unapproved_wording" in result["message"]


def test_quiet_hours_block_even_when_wording_needs_approval(service):
    seed(service, zone="Pacific/Honolulu")  # 06:00 recipient-local
    result = service.before("send_message", payload(message="unapproved synthetic"))
    assert result["action"] == "block" and "quiet_hours" in result["message"]


def test_non_send_never_opens_broken_storage_but_send_fails_closed(service):
    service.ledger.connect = lambda: (_ for _ in ()).throw(OSError("synthetic private text"))
    assert service.before("read_file", {"path": "demo.txt"}) is None
    assert service.before("terminal", {"command": "printf demo"}) is None
    result = service.before("send_message", payload())
    assert result["action"] == "block" and "synthetic private" not in result["message"]


def test_uninspectable_send_is_blocked_and_hashed_not_stored(service):
    result = service.before("terminal", {"command": "hermes send --to sms:+1-555-0100 --file demo.txt"})
    assert result["action"] == "block"
    with service.ledger.transaction() as db:
        assert db.execute("select rule from decisions").fetchone()[0] == "uninspectable"


def test_invalid_settings_block_recognized_sends(service):
    seed(service)
    service.config_error = True
    assert service.before("send_message", payload())["action"] == "block"
    assert service.before("terminal", {"command": "printf demo"}) is None


def test_parallel_routine_sends_only_one_can_pass(service):
    seed(service)
    def attempt(index):
        return service.before("send_message", payload(), tool_call_id=str(index))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count(None) == 1
    assert [r["action"] for r in results if r] == ["approve"] * 3


def test_block_in_batch_wins_regardless_of_order_without_reserving_any_send(service):
    seed(service)
    seed(service, recipient="+1-555-0101")
    with service.ledger.transaction() as db:
        service.ledger.optout(db, "+1-555-0101")
    calls = [{"name": "send_message", "arguments": payload(r)} for r in ("+1-555-0100", "+1-555-0101")]
    for batch in (calls, list(reversed(calls))):
        assert service.before("tool_call", {"calls": batch})["action"] == "block"
    with service.ledger.transaction() as db:
        assert db.execute("select count(*) from messages").fetchone()[0] == 0


def test_outer_batch_does_not_double_reserve_leaf_calls(service):
    seed(service)
    assert service.before("tool_call", {"calls": [{"name": "send_message", "arguments": payload()}]}) is None
    assert service.before("send_message", payload()) is None


def test_cancelled_send_releases_pending_but_ambiguous_failure_stays_held(service):
    seed(service)
    service.before("send_message", payload(), tool_call_id="one")
    service.after("send_message", payload(), result="{}", status="cancelled", tool_call_id="one")
    assert service.before("send_message", payload(), tool_call_id="two") is None
    service.after("send_message", payload(), result='{"error":"synthetic adapter failure"}', status="error", tool_call_id="two")
    assert service.before("send_message", payload(), tool_call_id="three")["action"] == "approve"


def test_approval_scope_is_exact_payload_bound(service):
    seed(service)
    a = service.before("send_message", payload(message="synthetic A"))
    b = service.before("send_message", payload(message="synthetic B"))
    assert a["action"] == b["action"] == "approve"
    assert a["rule_key"] != b["rule_key"]
