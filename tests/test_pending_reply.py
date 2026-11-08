from test_service import service, seed, payload
from test_inbound import source


def test_inbound_reply_while_send_pending_cannot_unlock_second_send(service):
    seed(service)
    service.before("send_message", payload(), tool_call_id="one")
    service.inbound(platform="sms", source=source(), message_id="reply-1", text="synthetic reply")
    assert service.before("send_message", payload(), tool_call_id="two")["action"] == "approve"
