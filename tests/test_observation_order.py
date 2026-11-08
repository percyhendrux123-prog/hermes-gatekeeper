from test_service import service, seed, payload


def test_reply_before_send_completion_does_not_clear_eventual_outbound(service):
    from gatekeeper.history import reply
    seed(service)
    service.before("send_message", payload(), tool_call_id="one")
    with service.ledger.transaction() as db:
        reply(db, "+1-555-0100", "sms", "", at=service.now().timestamp())
    service.after("send_message", payload(), result='{"success":true}', status="ok", tool_call_id="one")
    assert service.before("send_message", payload(), tool_call_id="two")["action"] == "approve"


def test_uncorrelated_cancel_cannot_release_newer_identical_attempt(service):
    seed(service)
    service.before("send_message", payload())
    service.after("send_message", payload(), result="{}", status="cancelled")
    assert service.before("send_message", payload())["action"] == "approve"
