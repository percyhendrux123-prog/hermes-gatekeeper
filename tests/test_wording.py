import pytest


@pytest.mark.parametrize("message,expected", [
    ("Demo notice for TEST.", None),
    ("Demo notice for TEST. ", ("approve", "unapproved_wording")),
    ("demo notice for TEST.", ("approve", "unapproved_wording")),
    ("Demo notice for OTHER.", ("approve", "unapproved_wording")),
])
def test_only_exact_owner_filled_templates_pass(message, expected):
    from gatekeeper.wording import check
    assert check(message, ["Demo notice for ${topic}."], {"topic": "TEST"}) == expected


def test_no_templates_or_missing_variables_never_auto_approve():
    from gatekeeper.wording import check
    assert check("demo", [], {}) == ("approve", "unapproved_wording")
    assert check("demo", ["$missing"], {}) == ("approve", "unapproved_wording")
    assert check("$literal", ["$$literal"], {}) is None


@pytest.mark.parametrize("template", ["$", "${broken", "${person.name}", "${value[0]}"])
def test_malformed_templates_are_policy_errors(template):
    from gatekeeper.config import Settings
    with pytest.raises(ValueError):
        Settings.parse({"templates": [template]})


@pytest.mark.parametrize("variables", [{"x": 1}, {"x.y": "test"}, [], {"x": "a" * 4097}])
def test_owner_variables_are_plain_bounded_strings(variables):
    from gatekeeper.wording import validate_variables
    with pytest.raises(ValueError):
        validate_variables(variables)


def test_variables_cannot_evaluate_python_or_recursively_expand():
    from gatekeeper.wording import check, validate_variables
    variables = {"topic": "${other}"}
    assert validate_variables(variables) == variables
    assert check("${other}", ["$topic"], variables) is None
    assert check("executed", ["$topic"], variables) == ("approve", "unapproved_wording")
