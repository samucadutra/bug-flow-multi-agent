from collections import Counter
from datetime import UTC, timedelta

from bugflow import enums
from bugflow.seed.bugs import SEED_BUGS


def _counts(field: str) -> dict[str, int]:
    return dict(Counter(getattr(bug, field) for bug in SEED_BUGS))


def test_twenty_unique_bugs():
    assert len(SEED_BUGS) == 20
    assert len({bug.title for bug in SEED_BUGS}) == 20


def test_field_limits_and_enums():
    for bug in SEED_BUGS:
        assert 1 <= len(bug.title) <= 120
        assert 1 <= len(bug.description) <= 5000
        assert 1 <= len(bug.reproduction_steps) <= 5000
        assert 1 <= len(bug.system_version) <= 50
        assert bug.environment in enums.codes(enums.Environment)
        assert bug.reporting_team in enums.codes(enums.Team)
        assert bug.intended_component in enums.codes(enums.Component)
        assert bug.intended_severity in enums.codes(enums.Severity)


def test_environment_distribution():
    assert _counts("environment") == {
        "production": 8,
        "staging": 5,
        "development": 4,
        "testing": 3,
    }


def test_team_distribution():
    assert _counts("reporting_team") == {
        "qa": 5,
        "support": 5,
        "product": 2,
        "frontend": 2,
        "backend": 2,
        "devops": 2,
        "data": 1,
        "security": 1,
    }


def test_intended_component_distribution():
    assert _counts("intended_component") == {
        "frontend": 3,
        "backend": 4,
        "database": 3,
        "devops": 2,
        "security": 2,
        "integration": 2,
        "ui_ux": 2,
        "infrastructure": 2,
    }


def test_intended_severity_distribution():
    assert _counts("intended_severity") == {"critical": 4, "major": 9, "minor": 7}


def test_opened_at_window():
    dates = [bug.opened_at for bug in SEED_BUGS]
    assert all(d.tzinfo is not None and d.utcoffset() == timedelta(0) for d in dates)
    assert all(d.tzinfo == UTC for d in dates)
    assert max(dates) - min(dates) <= timedelta(days=90)


def test_prd_examples_present():
    titles = {bug.title for bug in SEED_BUGS}
    assert "Checkout button does nothing on Safari 17" in titles
    assert "Nightly sales report times out after index change" in titles
    assert "API token visible in browser network logs" in titles
