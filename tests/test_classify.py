import pytest


def test_native_send_message_shape_and_explicit_thread():
    from gatekeeper.classify import classify
    send, = classify("send_message", {"target": "telegram:15550100:42", "message": "demo"})
    assert (send.channel, send.recipient, send.thread, send.message) == ("telegram", "15550100", "42", "demo")
    assert classify("send_message", {"action": "list"}) == []
    assert classify("web_search", {"query": "demo"}) == []
    send, = classify("send_message", {"target": "matrix:!demo:example.com", "message": "demo"})
    assert send.recipient == "!demo:example.com"


@pytest.mark.parametrize("args", [None, {}, {"action": "react"}, {"target": "sms", "message": "demo"},
    {"target": "sms:", "message": "demo"}, {"target": "sms:+1-555-0100", "message": ""},
    {"target": 1, "message": "demo"}, {"target": "sms:+1-555-0100", "message": ["demo"]},
    {"target": "sms:+1-555-0100", "message": "demo", "subject": "hidden"},
    {"target": "discord:#demo", "message": "demo"},
])
def test_uninspectable_native_send_is_never_exempt(args):
    from gatekeeper.classify import classify, Uninspectable
    with pytest.raises(Uninspectable):
        classify("send_message", args)


@pytest.mark.parametrize("command,channel", [
    ("hermes send --to sms:+1-555-0100 'Demo notice.'", "sms"),
    ("/usr/local/bin/hermes send -t telegram:15550100:42 'Demo notice.'", "telegram"),
    ("imsg send --to +1-555-0100 --text 'Demo notice.' --service sms", "sms"),
    ("imsg send --service imessage --to +1-555-0100 --text 'Demo notice.'", "imessage"),
    ("im\\sg send --service sms --to +1-555-0100 --text 'Demo notice.'", "sms"),
])
def test_simple_terminal_sends_are_inspected_without_execution(command, channel):
    from gatekeeper.classify import classify
    send, = classify("terminal", {"command": command})
    assert send.channel == channel
    assert send.message == "Demo notice."


@pytest.mark.parametrize("command", [
    "hermes send --to sms:+1-555-0100 --file demo.txt",
    "hermes send --to sms:+1-555-0100",
    "hermes send --to sms:+1-555-0100 --subject hidden demo",
    "hermes send --to sms:+1-555-0100 '$BODY'",
    "hermes send --to sms:+1-555-0100 `read-demo`",
    "imsg send --to +1-555-0100 --text demo",  # auto-service not a known channel
    "imsg send --chat-id 10 --text demo",
    "imsg send --service sms --to +1-555-0100 --text 'unterminated",
    "env DEMO=1 hermes send --to sms:+1-555-0100 demo",
    "sh -c 'hermes send --to sms:+1-555-0100 demo'",
    "printf demo | hermes send --to sms:+1-555-0100",
    "hermes send --to sms:+1-555-0100 demo; printf done",
    "hermes send --to sms:+1-555-0100 demo > demo.log",
    "hermes send --to sms:+1-555-0100 demo &",
])
def test_recognized_complex_or_hidden_body_terminal_sends_fail_closed(command):
    from gatekeeper.classify import classify, Uninspectable
    with pytest.raises(Uninspectable):
        classify("terminal", {"command": command})


def test_non_send_terminal_and_nested_deferred_batches():
    from gatekeeper.classify import classify
    assert classify("terminal", {"command": "printf demo"}) == []
    assert classify("terminal", {"command": "hermes send --list"}) == []
    batch = {"calls": [{"name": "functions.send_message", "arguments": {"target": "sms:+1-555-0100", "message": "demo"}}]}
    assert len(classify("tool_call", batch)) == 1
    outer = {"tool_uses": [{"recipient_name": "functions.tool_call", "parameters": batch}]}
    assert len(classify("multi_tool_use.parallel", outer)) == 1


@pytest.mark.parametrize("args", [{}, {"calls": {}}, {"calls": [None]}, {"calls": [{"name": "send_message"}]}])
def test_malformed_batches_fail_closed(args):
    from gatekeeper.classify import classify, Uninspectable
    with pytest.raises(Uninspectable):
        classify("tool_call", args)
