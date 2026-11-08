import pytest

from test_service import service, seed, payload


@pytest.mark.parametrize("command", [
    "imsg \\\nsend --service sms --to +1-555-0100 --text 'Demo notice.'",
    "hermes send --to sms:+1-555-0100 **Hello**",
    "hermes send --to sms:+1-555-0100 demo?",
    "hermes send --to sms:+1-555-0100 [ab]",
    "hermes send --to sms:+1-555-0100 {a,b}",
    "hermes send --to sms:+1-555-0100 ~",
    "hermes send --to sms:+1-555-0100 'Demo \\\nnotice.'",
])
def test_expansion_bearing_recognized_commands_are_blocked(command):
    from gatekeeper.classify import classify, Uninspectable
    with pytest.raises(Uninspectable):
        classify("terminal", {"command": command})


def test_expected_uninspectable_block_observer_does_not_poison_service(service):
    seed(service)
    args = {"command": "hermes send --to sms:+1-555-0100 --file demo.txt"}
    assert service.before("terminal", args)["action"] == "block"
    service.after("terminal", args, result="{}", status="blocked", tool_call_id="bad")
    assert service.before("send_message", payload()) is None
