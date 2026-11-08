import pytest

from test_service import service, seed, payload


def source(chat="+1-555-0100", user="+1-555-0100", kind="dm", thread=""):
    return {"user_id": user, "chat_id": chat, "chat_type": kind, "thread_id": thread}


def test_public_admitted_stop_suppresses_sender_and_dm_target_without_sending(service):
    seed(service)
    result = service.inbound(platform="sms", source=source(), message_id="demo-1", text=" stop ")
    assert result == {"action": "handled"}  # consume silently, no automatic reply
    assert "suppressed" in service.before("send_message", payload())["message"]
    assert service.command("consent +1-555-0100 sms test 2026-01-01 UTC", platform="cli")
    assert service.before("send_message", payload())["action"] == "block"


def test_different_sender_and_dm_destination_are_both_suppressed(service):
    from gatekeeper.suppression import check
    service.inbound(platform="discord", source=source("demo-dm-id", "demo-user-id"), message_id="1", text="QUIT")
    with service.ledger.transaction() as db:
        assert check(db, "demo-dm-id") == ("block", "suppressed")
        assert check(db, "demo-user-id") == ("block", "suppressed")


def test_admitted_dm_reply_clears_only_its_thread_and_never_grants_consent(service):
    seed(service)
    service.before("send_message", payload())
    assert service.inbound(platform="sms", source=source(), message_id="reply-1", text="synthetic reply") is None
    assert service.before("send_message", payload()) is None
    # Replay an old ingress event cannot clear a newer outbound reservation.
    service.inbound(platform="sms", source=source(), message_id="reply-1", text="synthetic reply")
    assert service.before("send_message", payload())["action"] == "approve"
    service.inbound(platform="sms", source=source("+1-555-0101", "+1-555-0101"), message_id="reply-2", text="synthetic reply")
    assert "no_consent" in service.before("send_message", payload("+1-555-0101"))["message"]


def test_group_reply_does_not_clear_dm_or_suppress_entire_group(service):
    from gatekeeper.suppression import check
    seed(service)
    service.before("send_message", payload())
    service.inbound(platform="sms", source=source("demo-group", "+1-555-0100", "group"), message_id="1", text="synthetic reply")
    assert service.before("send_message", payload())["action"] == "approve"
    service.inbound(platform="sms", source=source("demo-group", "+1-555-0100", "group"), message_id="2", text="STOP")
    with service.ledger.transaction() as db:
        assert check(db, "demo-group") is None
        assert check(db, "+1-555-0100") == ("block", "suppressed")


def test_inbound_storage_error_latches_send_block_even_after_storage_recovers(service):
    seed(service)
    connect = service.ledger.connect
    service.ledger.connect = lambda: (_ for _ in ()).throw(OSError("synthetic failure"))
    assert service.inbound(platform="sms", source=source(), message_id="1", text="STOP") == {"action": "handled"}
    service.ledger.connect = connect
    assert service.before("send_message", payload())["action"] == "block"


def test_stop_with_missing_identity_fails_closed_not_guessed(service):
    seed(service)
    assert service.inbound(platform="sms", source={}, message_id="1", text="STOP") == {"action": "handled"}
    assert service.before("send_message", payload())["action"] == "block"


def test_custom_stop_keyword_and_non_stop_phrase(service):
    from gatekeeper.config import Settings
    service.settings = Settings.parse({"stop_keywords": ["PAUSE"]})
    assert service.inbound(platform="sms", source=source(), message_id="1", text="please stop later") is None
    assert service.inbound(platform="sms", source=source(), message_id="2", text="pause") == {"action": "handled"}
