from datetime import datetime, timezone

import pytest


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


@pytest.mark.parametrize("instant,expected", [
    ("2026-01-01T13:59:59", ("block", "quiet_hours")),
    ("2026-01-01T14:00:00", None),
    ("2026-01-02T02:59:59", None),
    ("2026-01-02T03:00:00", ("block", "quiet_hours")),
    ("2026-07-01T13:00:00", None),
    ("2026-07-02T02:00:00", ("block", "quiet_hours")),
])
def test_recipient_local_boundaries_and_dst(instant, expected):
    from gatekeeper.quiet_hours import check
    assert check({"timezone": "America/Chicago"}, at(instant)) == expected


@pytest.mark.parametrize("zone", [None, "", "Unknown/Zone"])
def test_unknown_timezone_never_guessed(zone):
    from gatekeeper.quiet_hours import check
    assert check({"timezone": zone}, at("2026-01-01T16:00:00")) == ("approve", "unknown_timezone")


def test_owner_region_override_and_overnight_window():
    from gatekeeper.quiet_hours import check
    row = {"timezone": "UTC", "region": "TEST"}
    assert check(row, at("2026-01-01T08:30:00"), overrides={"TEST": ["09:00", "20:00"]}) == ("block", "quiet_hours")
    assert check(row, at("2026-01-01T23:00:00"), start="22:00", end="06:00") is None
    assert check(row, at("2026-01-01T06:00:00"), start="22:00", end="06:00") == ("block", "quiet_hours")


@pytest.mark.parametrize("config", [
    {"require_consent": "false"}, {"min_gap_seconds": True}, {"min_gap_seconds": -1},
    {"start": "8:00"}, {"start": "24:00"}, {"start": "08:00", "end": "08:00"},
    {"region_windows": {"TEST": ["09:00"]}}, {"region_windows": []},
    {"stop_keywords": []}, {"stop_keywords": "STOP"}, {"stop_keywords": [1]},
    {"templates": "hello"}, {"templates": [None]}, {"unknown_setting": True},
])
def test_settings_reject_unsafe_values(config):
    from gatekeeper.config import Settings
    with pytest.raises(ValueError):
        Settings.parse(config)


def test_settings_defaults_and_explicit_optout_of_consent_requirement():
    from gatekeeper.config import Settings
    defaults = Settings.parse({})
    assert defaults.require_consent is True
    assert (defaults.start, defaults.end, defaults.min_gap_seconds) == ("08:00", "21:00", 0)
    assert Settings.parse({"require_consent": False}).require_consent is False
    assert Settings.parse({"stop_keywords": ["pause"]}).stop_keywords == ("PAUSE",)
