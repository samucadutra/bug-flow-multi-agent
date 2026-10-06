import re

import pytest

from bugflow import enums

PRD_CODES = {
    "BugStatus": ["open", "processing", "processed", "failed"],
    "Environment": ["production", "staging", "development", "testing"],
    "Team": ["frontend", "backend", "data", "devops", "security", "qa", "support", "product"],
    "Component": [
        "frontend",
        "backend",
        "database",
        "devops",
        "security",
        "integration",
        "ui_ux",
        "infrastructure",
    ],
    "Severity": ["critical", "major", "minor"],
    "ResolutionStatus": ["planned", "needs_info", "deferred", "wont_fix"],
    "Priority": ["urgent", "high", "medium", "low"],
    "Seniority": ["junior", "mid", "senior", "lead"],
    "RunType": ["triage", "index", "seed", "init", "reset"],
    "RunStatus": ["queued", "running", "succeeded", "failed"],
    "StepStatus": ["pending", "running", "succeeded", "failed", "skipped"],
}


@pytest.mark.parametrize("name", list(PRD_CODES))
def test_codes_match_prd_tables(name):
    assert enums.codes(getattr(enums, name)) == PRD_CODES[name]


def test_codes_are_snake_case_and_unique():
    for enum_cls in enums.ENUM_CLASSES:
        codes = enums.codes(enum_cls)
        assert len(codes) == len(set(codes))
        assert all(re.fullmatch(r"[a-z]+(_[a-z]+)*", code) for code in codes)


def test_every_member_has_label():
    for enum_cls in enums.ENUM_CLASSES:
        labels = [enums.label_of(member) for member in enum_cls]
        assert all(labels)
        assert len(labels) == len(set(labels))


def test_label_overrides():
    assert enums.label_of(enums.Component.UI_UX) == "UI/UX"
    assert enums.label_of(enums.ResolutionStatus.WONT_FIX) == "Won't fix"
    assert enums.label_of(enums.ResolutionStatus.NEEDS_INFO) == "Needs info"
    assert enums.label_of(enums.Team.DEVOPS) == "DevOps"
    assert enums.label_of(enums.Team.QA) == "QA"


def test_component_and_severity_definitions():
    for enum_cls in enums.ENUM_CLASSES:
        for member in enum_cls:
            definition = enums.definition_of(member)
            if enum_cls in (enums.Component, enums.Severity):
                assert definition
            else:
                assert definition is None
    assert "data loss" in enums.definition_of(enums.Severity.CRITICAL)


def test_all_enums_descriptor_order():
    descriptors = enums.all_enums()
    assert [d.name for d in descriptors] == list(PRD_CODES)
    for descriptor in descriptors:
        assert [v.code for v in descriptor.values] == PRD_CODES[descriptor.name]
        assert all(v.label for v in descriptor.values)
