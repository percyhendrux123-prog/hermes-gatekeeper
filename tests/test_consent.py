import sqlite3

import pytest


@pytest.fixture
def ledger(tmp_path):
    from gatekeeper.storage import Ledger
    return Ledger(lambda: sqlite3.connect(tmp_path / "state.db"))


def test_consent_is_channel_specific_and_optout_stays_absolute(ledger):
    from gatekeeper import consent, suppression
    with ledger.transaction() as db:
        assert consent.check(db, "+1-555-0100", "sms") == ("block", "no_consent")
        consent.record(db, "+1-555-0100", "sms", "owner-test", "2026-01-01", "America/Chicago")
        assert consent.check(db, "+1-555-0100", "sms") is None
        assert consent.check(db, "+1-555-0100", "signal") == ("block", "no_consent")
        assert consent.check(db, "+1-555-0100", "signal", require=False) is None
        ledger.optout(db, "+1-555-0100")
        consent.record(db, "+1-555-0100", "sms", "renewed-test", "2026-01-02", "UTC")
        assert suppression.check(db, "+1-555-0100") == ("block", "suppressed")


def test_contact_metadata_and_revocation(ledger):
    from gatekeeper import consent
    with ledger.transaction() as db:
        consent.record(db, "demo@example.com", "email", "synthetic-form", "2026-01-01", "UTC", "TEST")
        row = consent.contact(db, "demo@example.com", "email")
        assert (row["source"], row["date"], row["timezone"], row["region"]) == ("synthetic-form", "2026-01-01", "UTC", "TEST")
        consent.revoke(db, "demo@example.com", "email")
        assert consent.check(db, "demo@example.com", "email") == ("block", "no_consent")


@pytest.mark.parametrize("channel,source,date,zone", [
    ("SMS space", "test", "2026-01-01", "UTC"),
    ("sms", "", "2026-01-01", "UTC"),
    ("sms", "test", "not-a-date", "UTC"),
    ("sms", "test", "2026-01-01", "Unknown/Zone"),
])
def test_invalid_consent_never_commits(ledger, channel, source, date, zone):
    from gatekeeper import consent
    with pytest.raises(ValueError):
        with ledger.transaction() as db:
            consent.record(db, "+1-555-0100", channel, source, date, zone)


def test_missing_timezone_is_allowed_as_unknown_record(ledger):
    from gatekeeper import consent
    with ledger.transaction() as db:
        consent.record(db, "+1-555-0100", "sms", "test", "2026-01-01", "")
        assert consent.contact(db, "+1-555-0100", "sms")["timezone"] == ""
