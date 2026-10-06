import pytest

from bugflow.enums import Environment, Team
from bugflow.services.errors import ValidationFailedError
from bugflow.services.schemas import BugCreate, BugUpdate, validate_payload

VALID = {
    "title": "Checkout button does nothing",
    "description": "Clicking Place order shows no response.",
    "reproduction_steps": "1. Add an item. 2. Click Place order.",
    "system_version": "web 3.8.2",
    "environment": "production",
    "reporting_team": "support",
}


def errors_of(payload, model=BugCreate):
    with pytest.raises(ValidationFailedError) as caught:
        validate_payload(model, payload)
    return {(e.field, e.message) for e in caught.value.field_errors}


def test_valid_payload_accepted():
    bug = validate_payload(BugCreate, VALID)
    assert bug.environment is Environment.PRODUCTION
    assert bug.reporting_team is Team.SUPPORT


def test_boundaries_accepted():
    payload = {
        **VALID,
        "title": "t" * 120,
        "description": "d" * 5000,
        "reproduction_steps": "r" * 5000,
        "system_version": "v" * 50,
    }
    assert len(validate_payload(BugCreate, payload).description) == 5000


@pytest.mark.parametrize(
    ("field", "limit"),
    [("title", 120), ("description", 5000), ("reproduction_steps", 5000), ("system_version", 50)],
)
def test_over_length_rejected_per_field(field, limit):
    assert errors_of({**VALID, field: "x" * (limit + 1)}) == {
        (field, f"must be at most {limit} characters")
    }


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_and_whitespace_only_rejected(value):
    assert errors_of({**VALID, "title": value}) == {("title", "must not be empty")}


def test_values_are_not_trimmed():
    assert validate_payload(BugCreate, {**VALID, "title": "  padded  "}).title == "  padded  "


@pytest.mark.parametrize(
    ("field", "value", "codes"),
    [
        ("environment", "sandbox", "production, staging, development, testing"),
        ("environment", "Production", "production, staging, development, testing"),
        ("reporting_team", "QA", "frontend, backend, data, devops, security, qa, support, product"),
    ],
)
def test_invalid_enum_lists_allowed_codes(field, value, codes):
    errors = errors_of({**VALID, field: value})
    assert errors == {(field, f"must be one of: {codes}")}
    assert value not in next(iter(errors))[1].split(": ")[0]


def test_multiple_errors_reported_together():
    errors = errors_of({**VALID, "title": "", "system_version": "v" * 51})
    assert {field for field, _ in errors} == {"title", "system_version"}


def test_missing_and_unknown_fields():
    payload = {k: v for k, v in VALID.items() if k != "title"} | {"extra": 1}
    assert errors_of(payload) == {("title", "is required"), ("extra", "is not allowed")}


def test_wrong_type_is_invalid_without_value():
    assert errors_of({**VALID, "title": 12345}) == {("title", "is invalid")}


def test_direct_construction_raises_service_error():
    with pytest.raises(ValidationFailedError) as caught:
        BugCreate(**{**VALID, "title": "x" * 121})
    assert [e.field for e in caught.value.field_errors] == ["title"]


def test_update_requires_a_field():
    assert errors_of({}, BugUpdate) == {("update", "at least one field is required")}


def test_update_with_a_field_and_changes():
    update = validate_payload(BugUpdate, {"title": "New", "environment": "staging"})
    assert update.changes() == {"title": "New", "environment": "staging"}


@pytest.mark.parametrize("field", ["status", "opened_at", "updated_at", "id"])
def test_update_forbids_status_and_dates(field):
    assert (field, "is not allowed") in errors_of({"title": "x", field: "open"}, BugUpdate)


def test_error_text_never_contains_value():
    secret = "sk-test-canary-1234567890abcdef"
    errors = errors_of({**VALID, "environment": secret})
    assert all(secret not in message for _, message in errors)
