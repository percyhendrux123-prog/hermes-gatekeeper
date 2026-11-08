from test_double_text import ledger


def test_replayed_finish_cannot_release_older_matching_reservations(ledger):
    from gatekeeper.history import reserve, finish
    with ledger.transaction() as db:
        reserve(db, "demo@example.com", "email", "", at=1, call_key="same", decision=1)
        reserve(db, "demo@example.com", "email", "", at=2, call_key="same", decision=2)
        finish(db, "same", "failed")
        finish(db, "same", "failed")
        assert [r[0] for r in db.execute("select state from messages order by id")] == ["pending", "failed"]
