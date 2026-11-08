import sqlite3

import pytest

from test_service import service, seed, payload


def test_log_failure_never_turns_routine_send_into_pass(service, monkeypatch):
    seed(service)
    def failed(*args, **kwargs):
        raise OSError("synthetic secret message must not be echoed")
    monkeypatch.setattr(service.ledger, "log", failed)
    decision = service.before("send_message", payload())
    assert decision["action"] == "block"
    assert "secret" not in decision["message"]
    with service.ledger.transaction() as db:
        assert db.execute("select count(*) from messages").fetchone()[0] == 0


def test_commit_failure_never_returns_a_pass(service):
    seed(service)
    connect = service.ledger.connect
    with connect() as db:
        path = db.execute("pragma database_list").fetchone()[2]
    db.close()
    class BrokenCommit(sqlite3.Connection):
        def commit(self):
            raise sqlite3.OperationalError("synthetic commit failure")
    service.ledger.connect = lambda: sqlite3.connect(path, factory=BrokenCommit)
    assert service.before("send_message", payload())["action"] == "block"
    service.ledger.connect = connect
    with service.ledger.transaction() as db:
        assert db.execute("select count(*) from messages").fetchone()[0] == 0


def test_unexpected_classifier_exception_is_a_block(service, monkeypatch):
    import gatekeeper.service as module
    def failed(*args):
        raise RuntimeError("synthetic error")
    monkeypatch.setattr(module, "classify", failed)
    assert service.before("send_message", payload())["action"] == "block"


def test_observer_storage_failure_is_fail_closed_after_recovery(service):
    seed(service)
    service.before("send_message", payload(), tool_call_id="one")
    connect = service.ledger.connect
    service.ledger.connect = lambda: (_ for _ in ()).throw(OSError("synthetic observer failure"))
    service.after("send_message", payload(), result='{"success":true}', status="ok", tool_call_id="one")
    service.ledger.connect = connect
    assert service.before("send_message", payload())["action"] == "block"


def test_literal_terminal_success_is_logged_only_with_matching_call_identity(service):
    seed(service)
    args = {"command": "hermes send --to sms:+1-555-0100 'Demo notice.'"}
    assert service.before("terminal", args, session_id="demo", tool_call_id="one") is None
    service.after("terminal", args, result='{"exit_code":0}', status="ok", session_id="other", tool_call_id="one")
    with service.ledger.transaction() as db:
        assert db.execute("select state from messages").fetchone()[0] == "pending"
    service.after("terminal", args, result='{"exit_code":0}', status="ok", session_id="demo", tool_call_id="one")
    with service.ledger.transaction() as db:
        assert db.execute("select state from messages").fetchone()[0] == "sent"


@pytest.mark.parametrize("message", ["\ud800", "\udfff"])
def test_surrogate_message_cannot_auto_match_different_delivered_text(service, message):
    assert service.before("send_message", payload(message=message))["action"] == "block"


def test_no_model_fill_variables_are_accepted(service):
    seed(service)
    assert service.before("send_message", {**payload(), "variables": {"topic": "TEST"}})["action"] == "block"


def test_recursive_wrapper_limit_and_duplicate_terminal_options():
    from gatekeeper.classify import classify, Uninspectable
    args = payload()
    tool = "send_message"
    for _ in range(10):
        args, tool = {"calls": [{"name": tool, "arguments": args}]}, "tool_call"
    with pytest.raises(Uninspectable):
        classify(tool, args)
    with pytest.raises(Uninspectable):
        classify("terminal", {"command": "hermes send --to sms:+1-555-0100 -t sms:+1-555-0101 demo"})


def test_storage_validation_does_not_accept_malformed_ids(service):
    from gatekeeper.storage import recipient_id, thread_id
    for value in (None, "", "demo recipient", "a" * 257):
        with pytest.raises(ValueError):
            recipient_id(value)
    with pytest.raises(ValueError):
        thread_id(1)


def test_unchanged_non_send_observers_and_local_ingress_do_not_create_records(service):
    assert service.after("read_file", {}, result="unstructured", status="ok") is None
    assert service.inbound(platform="cli", source=None, text="STOP") is None
    with service.ledger.transaction() as db:
        assert db.execute("select count(*) from decisions").fetchone()[0] == 0
