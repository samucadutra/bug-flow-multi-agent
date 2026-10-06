from collections import Counter

import pytest
from sqlalchemy import select, text

from bugflow.db.models import Bug
from bugflow.seed.bugs import SEED_BUGS
from bugflow.services.db_admin import seed_db

pytestmark = pytest.mark.integration


def _bugs(session):
    return list(session.scalars(select(Bug)))


def test_creates_twenty_open_bugs(session):
    result = seed_db(session)
    bugs = _bugs(session)
    assert (result.created, result.already_present) == (20, 0)
    assert len(bugs) == 20
    assert {bug.status for bug in bugs} == {"open"}
    dates = [bug.opened_at for bug in bugs]
    assert (max(dates) - min(dates)).days <= 90


def test_distribution_by_environment_and_team(session):
    seed_db(session)
    bugs = _bugs(session)
    assert Counter(b.environment for b in bugs) == {
        "production": 8,
        "staging": 5,
        "development": 4,
        "testing": 3,
    }
    assert Counter(b.reporting_team for b in bugs) == {
        "qa": 5,
        "support": 5,
        "product": 2,
        "frontend": 2,
        "backend": 2,
        "devops": 2,
        "data": 1,
        "security": 1,
    }


def test_second_run_adds_nothing(session):
    seed_db(session)
    result = seed_db(session)
    assert (result.created, result.already_present) == (0, 20)
    bugs = _bugs(session)
    assert len(bugs) == 20
    assert len({b.title for b in bugs}) == 20


def test_partial_presence_inserts_only_missing(session):
    seed_db(session)
    session.execute(
        text("DELETE FROM bugs WHERE title = ANY(:titles)"),
        {"titles": [SEED_BUGS[0].title, SEED_BUGS[1].title, SEED_BUGS[2].title]},
    )
    session.commit()
    result = seed_db(session)
    assert (result.created, result.already_present) == (3, 17)
    assert len(_bugs(session)) == 20


def test_seed_is_atomic_on_failure(session, monkeypatch):
    from bugflow.services import db_admin

    broken = db_admin.SEED_BUGS[:-1] + (
        type(db_admin.SEED_BUGS[-1])(
            **{**db_admin.SEED_BUGS[-1].__dict__, "environment": "sandbox"}
        ),
    )
    monkeypatch.setattr(db_admin, "SEED_BUGS", broken)
    with pytest.raises(Exception, match="ck_bugs_environment"):
        seed_db(session)
    assert _bugs(session) == []


def test_matches_by_title(session):
    session.add(
        Bug(
            title=SEED_BUGS[0].title,
            description="Different text",
            reproduction_steps="Different steps",
            system_version="other 1.0",
            environment="testing",
            reporting_team="qa",
        )
    )
    session.commit()
    result = seed_db(session)
    assert (result.created, result.already_present) == (19, 1)
    assert len(_bugs(session)) == 20
