import sqlite3

import pytest


@pytest.fixture
def ledger(tmp_path):
    from gatekeeper.storage import Ledger
    return Ledger(lambda: sqlite3.connect(tmp_path / "state.db"))


def test_unanswered_pending_and_confirmed_sends_hold_until_reply(ledger):
    from gatekeeper import double_text
    from gatekeeper.history import reserve, reply, finish
    with ledger.transaction() as db:
        args = ("+1-555-0100", "sms", "demo-thread")
        assert double_text.check(db, *args, now=100) is None
        reserve(db, *args, at=100, call_key="key1", decision=1)
        assert double_text.check(db, *args, now=200) == ("approve", "unanswered")
        assert double_text.check(db, "+1-555-0101", "sms", "demo-thread", now=200) is None
        assert double_text.check(db, "+1-555-0100", "sms", "other-thread", now=200) is None
        assert double_text.check(db, "+1-555-0100", "signal", "demo-thread", now=200) is None
        finish(db, "key1", "sent")
        assert double_text.check(db, *args, now=100000) == ("approve", "unanswered")
        reply(db, *args, at=200)
        assert double_text.check(db, *args, now=201) is None
        assert double_text.check(db, *args, now=201, min_gap=120) == ("approve", "minimum_gap")
        assert double_text.check(db, *args, now=220, min_gap=120) is None


def test_blocked_or_cancelled_reservation_does_not_invent_sent_message(ledger):
    from gatekeeper import double_text
    from gatekeeper.history import reserve, finish
    with ledger.transaction() as db:
        args = ("+1-555-0100", "sms", "")
        reserve(db, *args, at=100, call_key="key1", decision=1)
        finish(db, "key1", "failed")
        assert double_text.check(db, *args, now=101) is None
        reserve(db, *args, at=102, call_key="key2", decision=2)
        finish(db, "key1", "sent")  # late duplicate observer cannot revive a failed reservation
        assert double_text.check(db, *args, now=103) == ("approve", "unanswered")


def test_latest_matching_reservation_only_is_finished(ledger):
    from gatekeeper.history import reserve, finish
    with ledger.transaction() as db:
        reserve(db, "demo@example.com", "email", "", at=1, call_key="same", decision=1)
        reserve(db, "demo@example.com", "email", "", at=2, call_key="same", decision=2)
        finish(db, "same", "failed")
        assert [r[0] for r in db.execute("select state from messages order by id")] == ["pending", "failed"]
