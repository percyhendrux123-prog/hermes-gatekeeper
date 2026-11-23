"""Strict settings validation: a malformed policy must not weaken the gate."""
from dataclasses import dataclass, field, fields

from .quiet_hours import window
from .suppression import KEYWORDS
from .wording import validate_template


@dataclass(frozen=True)
class Settings:
    require_consent: bool = True
    start: str = "08:00"
    end: str = "21:00"
    region_windows: dict = field(default_factory=dict)
    min_gap_seconds: int = 0
    templates: tuple = ()
    stop_keywords: tuple = KEYWORDS
    escalate_unrecognized_sends: bool = True
    extra_send_tool_patterns: tuple = ()
    allow_tools: tuple = ()

    @classmethod
    def parse(cls, data):
        if not isinstance(data, dict) or set(data) - {f.name for f in fields(cls)}:
            raise ValueError("unknown settings")
        result = cls(**data)
        if type(result.require_consent) is not bool:
            raise ValueError("require_consent must be bool")
        if type(result.min_gap_seconds) is not int or not 0 <= result.min_gap_seconds <= 2678400:
            raise ValueError("invalid minimum gap")
        if type(result.escalate_unrecognized_sends) is not bool:
            raise ValueError("escalate_unrecognized_sends must be bool")
        for values in (result.extra_send_tool_patterns, result.allow_tools):
            if (not isinstance(values, (list, tuple)) or len(values) > 256 or
                    any(not isinstance(v, str) or not v or v.strip() != v or len(v) > 128 for v in values)):
                raise ValueError("invalid tool list")
        window(result.start, result.end)
        if not isinstance(result.region_windows, dict):
            raise ValueError("invalid region windows")
        for region, hours in result.region_windows.items():
            if not isinstance(region, str) or not region or not isinstance(hours, (list, tuple)) or len(hours) != 2:
                raise ValueError("invalid region window")
            window(*hours)
        for values in (result.templates, result.stop_keywords):
            if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in values):
                raise ValueError("invalid string list")
        if not result.stop_keywords or any(v.strip() != v or len(v.split()) != 1 for v in result.stop_keywords):
            raise ValueError("invalid STOP keywords")
        for text in result.templates:
            validate_template(text)
        return cls(**{**data, "templates": tuple(result.templates),
                      "stop_keywords": tuple(v.upper() for v in result.stop_keywords),
                      "extra_send_tool_patterns": tuple(result.extra_send_tool_patterns),
                      "allow_tools": tuple(result.allow_tools)})
