"""Exact comparison after simple owner-controlled $variable substitution."""
import re
from string import Template


def validate_template(text):
    if any(match.group("invalid") is not None for match in Template.pattern.finditer(text)):
        raise ValueError("invalid template")


def validate_variables(values):
    if not isinstance(values, dict) or len(values) > 64:
        raise ValueError("invalid variables")
    if any(not isinstance(k, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k)
           or not isinstance(v, str) or len(v) > 4096 for k, v in values.items()):
        raise ValueError("invalid variables")
    return values


def check(message, templates, variables):
    validate_variables(variables)
    for text in templates:
        try:
            if Template(text).substitute(variables) == message:
                return None
        except KeyError:
            continue
    return "approve", "unapproved_wording"
