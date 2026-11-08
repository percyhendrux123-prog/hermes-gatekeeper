"""Regressions found by running the plugin through a real Hermes host (invented data only)."""
from types import SimpleNamespace

import pytest

from test_service import service, seed, payload  # noqa: F401  (fixture re-export)


@pytest.mark.parametrize("command", [
    "hermes -p demo send --to sms:+1-555-0100 'Demo notice.'",
    "hermes --profile demo send --to sms:+1-555-0100 'Demo notice.'",
    "hermes --profile=demo send --to sms:+1-555-0100 'Demo notice.'",
    "/usr/local/bin/hermes -p demo send -t sms:+1-555-0100 'Demo notice.'",
    "hermes-agent send --to sms:+1-555-0100 'Demo notice.'",
])
def test_profile_selecting_global_options_do_not_hide_a_send(command):
    from gatekeeper.classify import classify
    send, = classify("terminal", {"command": command})
    assert (send.channel, send.recipient, send.message) == ("sms", "+15550100", "Demo notice.")


@pytest.mark.parametrize("command", [
    "hermes --yolo send --to sms:+1-555-0100 'Demo notice.'",   # unknown global option arity
    "hermes -p demo send",
    "hermes -p demo send --to sms:+1-555-0100",
    "python3 -m hermes_cli.main send --to sms:+1-555-0100 'Demo notice.'",
    "python3 -m hermes_cli.main -p demo send --to sms:+1-555-0100 'Demo notice.'",
    "hermes -p demo send --to sms:+1-555-0100 'unterminated",
    "python3 -m hermes_cli.main send --to sms:+1-555-0100 'unterminated",
])
def test_global_option_and_module_forms_fail_closed(command):
    from gatekeeper.classify import classify, Uninspectable
    with pytest.raises(Uninspectable):
        classify("terminal", {"command": command})


@pytest.mark.parametrize("command", [
    "hermes -p demo chat -q 'please send a summary'",
    "hermes --yolo chat -q 'send it'",
    "hermes -p demo gateway status",
    "hermes -p demo send --list",
    "hermes -p demo send --list telegram",
    "hermes chat",
    "python3 -m hermes_cli.main --version",
])
def test_non_send_hermes_commands_are_not_overblocked(command):
    from gatekeeper.classify import classify
    assert classify("terminal", {"command": command}) == []


def test_profile_flag_form_is_gated_like_the_plain_form(service):
    seed(service)
    with service.ledger.transaction() as db:
        service.ledger.optout(db, "+1-555-0100")
    for command in ("hermes send --to sms:+1-555-0100 'Demo notice.'",
                    "hermes -p demo send --to sms:+1-555-0100 'Demo notice.'"):
        result = service.before("terminal", {"command": command}, tool_call_id="one")
        assert result["action"] == "block" and "suppressed" in result["message"]


def test_suppression_is_case_insensitive_but_consent_stays_exact(service):
    seed(service, recipient="Demo@Example.com", channel="email")
    with service.ledger.transaction() as db:
        service.ledger.optout(db, "Demo@Example.com")
    for address in ("demo@example.com", "DEMO@EXAMPLE.COM", "Demo@Example.com"):
        result = service.before("send_message", {"target": "email:" + address, "message": "Demo notice."})
        assert result["action"] == "block" and "suppressed" in result["message"]


def test_case_variant_without_consent_is_blocked(service):
    seed(service, recipient="Demo@Example.com", channel="email")
    result = service.before("send_message", {"target": "email:demo@example.com", "message": "Demo notice."})
    assert result["action"] == "block" and "no_consent" in result["message"]


@pytest.mark.parametrize("platform,source", [
    ("local", SimpleNamespace(platform=SimpleNamespace(value="local"), chat_id="local")),  # gateway-owned local session
    ("local", {"platform": "local"}),
    ("cli", None), ("tui", None), ("desktop", None), ("local", None),
])
def test_gateway_dispatched_local_session_is_the_owner(service, platform, source):
    assert "ready" in service.command("", platform=platform, source=source)
    assert "consent recorded" in service.command("consent +1-555-0100 sms synthetic-form 2026-01-01 UTC",
                                                 platform=platform, source=source)


@pytest.mark.parametrize("platform,source", [
    ("telegram", SimpleNamespace(platform=SimpleNamespace(value="telegram"), chat_id="1", user_id="1")),
    ("telegram", SimpleNamespace(platform=SimpleNamespace(value="local"), chat_id="1")),  # forged local source
    ("local", SimpleNamespace(platform=SimpleNamespace(value="telegram"), chat_id="1")),
    ("local", SimpleNamespace(chat_id="1")),
    ("local", {"user_id": "demo"}),
    ("local", "local"),
    ("", None),
])
def test_remote_or_ambiguous_sources_are_still_refused(service, platform, source):
    assert "local owner" in service.command("optout +1-555-0100", platform=platform, source=source)
    with service.ledger.transaction() as db:
        assert db.execute("select count(*) from suppressions").fetchone()[0] == 0


@pytest.mark.parametrize("flag", ["--json", "-q", "--quiet", "--mention 15550100", "--subject hi", "--file x.txt"])
def test_unmodeled_hermes_send_flags_are_blocked_as_documented(flag):
    from gatekeeper.classify import classify, Uninspectable
    with pytest.raises(Uninspectable):
        classify("terminal", {"command": f"hermes send {flag} --to sms:+1-555-0100 'Demo notice.'"})
    with pytest.raises(Uninspectable):
        classify("terminal", {"command": "hermes send --to=sms:+1-555-0100 'Demo notice.'"})
