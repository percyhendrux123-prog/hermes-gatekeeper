import json

import pytest

from test_service import service, seed, payload


@pytest.mark.parametrize("platform,source", [("", None), ("telegram", None), ("discord", {"user_id": "demo"}), ("local", {}), ("cli", {})])
def test_remote_and_missing_context_cannot_read_or_mutate(service, platform, source):
    for raw in ("", "log", "optout +1-555-0100", "consent +1-555-0100 sms test 2026-01-01 UTC"):
        assert "local owner" in service.command(raw, platform=platform, source=source)
    with service.ledger.transaction() as db:
        assert db.execute("select count(*) from suppressions").fetchone()[0] == 0
        assert db.execute("select count(*) from contacts").fetchone()[0] == 0


@pytest.mark.parametrize("platform", ["cli", "tui", "desktop", "local"])
def test_owner_consent_optout_and_private_status_log(service, platform):
    def command(raw):
        return service.command(raw, platform=platform, source=None)
    assert "consent recorded" in command("consent +1-555-0100 sms synthetic-form 2026-01-01 UTC TEST")
    assert service.before("send_message", payload()) is None
    assert "+1-555-0100" not in command("log")
    assert "routine" in command("log 1")
    assert "suppressed" in command("optout +1-555-0100")
    assert "block" == service.before("send_message", payload())["action"]
    assert "consent recorded" in command("consent +1-555-0100 sms renewed 2026-01-01 UTC")
    assert "suppressed" in service.before("send_message", payload())["message"]
    assert "suppressed: 1" in command("")


def test_owner_reply_variables_and_revoke(service):
    seed(service)
    assert "variables saved" in service.command('variables +1-555-0100 sms \'{"topic":"TEST"}\'', platform="cli")
    with service.ledger.transaction() as db:
        assert json.loads(db.execute("select variables from contacts").fetchone()[0]) == {"topic": "TEST"}
    service.before("send_message", payload())
    assert "reply recorded" in service.command("reply +1-555-0100 sms", platform="cli")
    assert service.before("send_message", payload()) is None
    assert "consent revoked" in service.command("revoke +1-555-0100 sms", platform="cli")
    assert service.before("send_message", payload())["action"] == "block"


@pytest.mark.parametrize("raw", ["log 0", "log 51", "log nope", "optout", "unsuppress +1-555-0100", "consent +1-555-0100 sms test invalid UTC", "variables +1-555-0100 sms []", "'unterminated"])
def test_invalid_owner_commands_are_safe_and_useful(service, raw):
    result = service.command(raw, platform="cli")
    assert "Usage:" in result or "could not" in result


def test_storage_errors_are_not_exposed_in_owner_responses(service):
    service.ledger.connect = lambda: (_ for _ in ()).throw(OSError("synthetic private detail"))
    assert "could not" in service.command("", platform="cli")
    assert "synthetic private detail" not in service.command("", platform="cli")
