import json

import pytest
from pydantic import ValidationError

from bugflow.agents.outputs import (
    AGENT_KEYS,
    AGENTS,
    AnalysisOutput,
    ComponentOutput,
    DocumentOutput,
    PlanOutput,
    SeverityOutput,
)
from bugflow.enums import Component, Priority, ResolutionStatus, Seniority, Severity, Team
from mocks.fake_openai_server import default_reply


def parse(model, data):
    return model.model_validate_json(json.dumps(data))


def error_of(model, data):
    with pytest.raises(ValidationError) as caught:
        parse(model, data)
    return caught.value.errors()[0]


def with_field(role, **changes):
    data = default_reply(role)
    data.update(changes)
    return data


def test_agent_table_order_and_keys():
    assert AGENT_KEYS == (
        "component_classifier",
        "severity_classifier",
        "technical_analyst",
        "resolution_manager",
        "bug_documenter",
    )
    assert [agent.position for agent in AGENTS] == [1, 2, 3, 4, 5]
    assert [agent.label for agent in AGENTS][0] == "AG1 Component Classifier"
    assert all(len(agent.key) <= 30 for agent in AGENTS)
    for agent in AGENTS:
        assert agent.role and agent.goal and agent.backstory


@pytest.mark.parametrize(
    ("model", "role"),
    [
        (ComponentOutput, "Component Classifier"),
        (SeverityOutput, "Severity Classifier"),
        (AnalysisOutput, "Technical Analyst"),
        (PlanOutput, "Resolution Manager"),
        (DocumentOutput, "Bug Documenter"),
    ],
)
def test_canned_reply_is_valid_and_rejects_extras(model, role):
    assert parse(model, default_reply(role))
    assert error_of(model, with_field(role, extra_field=1))["type"] == "extra_forbidden"


@pytest.mark.parametrize("value", ["Backend", "backend ", " backend", "server-side", "BACKEND", ""])
def test_component_near_misses_rejected(value):
    assert (
        error_of(ComponentOutput, with_field("Component Classifier", component=value))["type"]
        == "enum"
    )


@pytest.mark.parametrize("value", ["high", "Major", "major ", "blocker"])
def test_severity_near_misses_rejected(value):
    assert (
        error_of(SeverityOutput, with_field("Severity Classifier", severity=value))["type"]
        == "enum"
    )


def test_every_enum_member_is_accepted():
    for member in Component:
        assert parse(ComponentOutput, with_field("Component Classifier", component=member.value))
    for severity in Severity:
        assert parse(SeverityOutput, with_field("Severity Classifier", severity=severity.value))


@pytest.mark.parametrize(("field", "limit"), [("justification", 600), ("user_impact", 400)])
def test_severity_text_boundaries(field, limit):
    data = default_reply("Severity Classifier")
    data[field] = "x" * limit
    assert parse(SeverityOutput, data)
    for bad in ("x" * (limit + 1), "", "   "):
        data[field] = bad
        assert error_of(SeverityOutput, data)["loc"] == (field,)


def test_component_justification_boundaries():
    data = default_reply("Component Classifier")
    data["justification"] = "x" * 600
    assert parse(ComponentOutput, data)
    data["justification"] = "x" * 601
    assert error_of(ComponentOutput, data)["loc"] == ("justification",)


@pytest.mark.parametrize(
    ("field", "limit"),
    [("root_cause", 800), ("technical_impact", 600), ("proposed_solution", 800)],
)
def test_analysis_text_boundaries(field, limit):
    data = default_reply("Technical Analyst")
    data[field] = "x" * limit
    assert parse(AnalysisOutput, data)
    data[field] = "x" * (limit + 1)
    assert error_of(AnalysisOutput, data)["loc"] == (field,)
    data[field] = ""
    assert error_of(AnalysisOutput, data)["loc"] == (field,)


def test_analysis_list_rules():
    data = default_reply("Technical Analyst")
    data["debugging_approach"] = ["a"] * 6
    assert parse(AnalysisOutput, data)
    for bad in ([], ["a"] * 7, [""], ["  "], [1]):
        data["debugging_approach"] = bad
        assert error_of(AnalysisOutput, data)["loc"][0] == "debugging_approach"
    data = default_reply("Technical Analyst")
    data["side_effects"] = []
    assert parse(AnalysisOutput, data)
    data["side_effects"] = ["a"] * 5
    assert parse(AnalysisOutput, data)
    data["side_effects"] = ["a"] * 6
    assert error_of(AnalysisOutput, data)["loc"] == ("side_effects",)


@pytest.mark.parametrize("bad", ["1", 1.5, [None], ["7"], [True]])
def test_referenced_ids_must_be_integers(bad):
    data = with_field("Technical Analyst", referenced_similar_bug_ids=bad)
    assert error_of(AnalysisOutput, data)["loc"][0] == "referenced_similar_bug_ids"


def test_referenced_ids_accept_integers():
    data = with_field("Technical Analyst", referenced_similar_bug_ids=[1, 22])
    assert parse(AnalysisOutput, data).referenced_similar_bug_ids == [1, 22]


@pytest.mark.parametrize(("days", "ok"), [(0, False), (1, True), (90, True), (91, False)])
def test_target_days_bounds(days, ok):
    data = with_field("Resolution Manager", target_days=days)
    if ok:
        assert parse(PlanOutput, data).target_days == days
    else:
        assert error_of(PlanOutput, data)["loc"] == ("target_days",)


@pytest.mark.parametrize("bad", ["5", 5.0, 5.5, True, None])
def test_target_days_must_be_an_integer(bad):
    assert error_of(PlanOutput, with_field("Resolution Manager", target_days=bad))["loc"] == (
        "target_days",
    )


def test_plan_rejects_a_persons_name():
    error = error_of(PlanOutput, with_field("Resolution Manager", assignee_name="Alice"))
    assert error["type"] == "extra_forbidden" and error["loc"] == ("assignee_name",)


def test_plan_enums_and_profile():
    plan = parse(PlanOutput, default_reply("Resolution Manager"))
    assert plan.resolution_status is ResolutionStatus.PLANNED
    assert plan.assigned_team is Team.BACKEND and plan.priority is Priority.HIGH
    assert plan.assignee_profile.seniority is Seniority.SENIOR
    for field, value in (
        ("resolution_status", "Planned"),
        ("assigned_team", "Backend"),
        ("priority", "urgent "),
    ):
        assert (
            error_of(PlanOutput, with_field("Resolution Manager", **{field: value}))["type"]
            == "enum"
        )


def test_plan_nested_rules():
    data = default_reply("Resolution Manager")
    data["assignee_profile"]["extra"] = 1
    error = error_of(PlanOutput, data)
    assert error["type"] == "extra_forbidden" and error["loc"] == ("assignee_profile", "extra")
    data = default_reply("Resolution Manager")
    data["assignee_profile"]["skills"] = []
    assert error_of(PlanOutput, data)["loc"] == ("assignee_profile", "skills")
    data["assignee_profile"]["skills"] = ["a"] * 7
    assert error_of(PlanOutput, data)["loc"] == ("assignee_profile", "skills")
    data["assignee_profile"]["skills"] = ["a"] * 6
    assert parse(PlanOutput, data)
    data["assignee_profile"]["seniority"] = "Senior"
    assert error_of(PlanOutput, data)["loc"] == ("assignee_profile", "seniority")


def test_plan_notes_may_be_empty_but_not_too_long():
    assert parse(PlanOutput, with_field("Resolution Manager", notes="")).notes == ""
    assert error_of(PlanOutput, with_field("Resolution Manager", notes="x" * 601))["loc"] == (
        "notes",
    )


def test_document_rules():
    data = default_reply("Bug Documenter")
    data["key_takeaways"] = ["a"] * 5
    data["next_steps"] = ["a"] * 5
    assert parse(DocumentOutput, data)
    for field in ("key_takeaways", "next_steps"):
        for bad in ([], ["a"] * 6, [""]):
            changed = default_reply("Bug Documenter")
            changed[field] = bad
            assert error_of(DocumentOutput, changed)["loc"][0] == field
    data["executive_summary"] = "x" * 601
    assert error_of(DocumentOutput, data)["loc"] == ("executive_summary",)


def test_missing_required_field_is_rejected_without_default():
    for model, role in (
        (ComponentOutput, "Component Classifier"),
        (PlanOutput, "Resolution Manager"),
    ):
        data = default_reply(role)
        first = next(iter(data))
        del data[first]
        assert error_of(model, data)["type"] == "missing"
