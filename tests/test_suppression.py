import sqlite3
from contextlib import closing

import pytest


def test_optout_survives_reload_and_normalizes_phone_format(tmp_path):
    from gatekeeper.storage import Ledger, recipient_id
    from gatekeeper.suppression import check, is_stop
    path = tmp_path / "state.db"
    ledger = Ledger(lambda: sqlite3.connect(path))
    with ledger.transaction() as db:
        ledger.optout(db, "+1-555-0100")
    with Ledger(lambda: sqlite3.connect(path)).transaction() as db:
        assert check(db, "+15550100") == ("block", "suppressed")
        assert check(db, "+1-555-0101") is None
        assert db.execute("select recipient_id from suppressions").fetchone()[0] == recipient_id("+15550100")
    assert is_stop("  stopALL ")
    assert not is_stop("please stop later")
    assert is_stop("PAUSE", ("PAUSE",))


@pytest.mark.parametrize("text", ["STOP", "STOPALL", "UNSUBSCRIBE", "CANCEL", "END", "QUIT", " stop\n"])
def test_stop_keywords(text):
    from gatekeeper.suppression import is_stop
    assert is_stop(text)


def test_decisions_are_private_and_connections_close(tmp_path):
    from gatekeeper.storage import Ledger, body_hash, recipient_id, thread_id
    path = tmp_path / "state.db"
    connections = []
    def connect():
        db = sqlite3.connect(path)
        connections.append(db)
        return db
    ledger = Ledger(connect)
    with ledger.transaction() as db:
        ledger.log(db, "sms", "+1-555-0100", "", "synthetic wording", "suppressed", "block", 1.0)
    with closing(sqlite3.connect(path)) as db:
        row = db.execute("select at,channel,recipient_id,thread_id,body_hash,rule,outcome from decisions").fetchone()
        assert row == (1.0, "sms", recipient_id("+1-555-0100"), thread_id(""), body_hash("synthetic wording"), "suppressed", "block")
        assert "synthetic wording".encode() not in path.read_bytes()
        assert b"+1-555-0100" not in path.read_bytes()
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("select 1")


def test_transaction_rolls_back_and_preserves_existing_state(tmp_path):
    from gatekeeper.storage import Ledger
    ledger = Ledger(lambda: sqlite3.connect(tmp_path / "state.db"))
    with pytest.raises(RuntimeError):
        with ledger.transaction() as db:
            ledger.optout(db, "+1-555-0100")
            raise RuntimeError("synthetic failure")
    with ledger.transaction() as db:
        assert db.execute("select count(*) from suppressions").fetchone()[0] == 0
