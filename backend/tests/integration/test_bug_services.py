import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from bugflow.db.engine import session_factory
from bugflow.db.models import Bug
from bugflow.enums import BugStatus, Environment, Team
from bugflow.services.bugs import create_bug, get_bug, update_bug
from bugflow.services.errors import NotFoundError, StateConflictError, ValidationFailedError
from bugflow.services.schemas import BugCreate, BugUpdate

pytestmark = pytest.mark.integration

VALID = {
    "title": "Checkout button does nothing",
    "description": "Clicking Place order shows no response.",
    "reproduction_steps": "1. Add an item. 2. Click Place order.",
    "system_version": "web 3.8.2",
    "environment": "production",
    "reporting_team": "support",
}


def make_bug(session: Session, status: str = "open", **overrides) -> int:
    values = {
        "title": "Open bug",
        "description": "An open bug used by items.",
        "reproduction_steps": "1. Open it.",
        "system_version": "web 1.0.0",
        "environment": "testing",
        "reporting_team": "qa",
        "status": status,
    } | overrides
    bug = Bug(**values)
    session.add(bug)
    session.commit()
    return bug.id


def test_create_returns_open_bug(session):
    bug = create_bug(session, BugCreate(**VALID))
    assert bug.status is BugStatus.OPEN
    assert bug.id > 0
    assert bug.opened_at is not None and bug.updated_at is not None
    assert bug.environment is Environment.PRODUCTION and bug.reporting_team is Team.SUPPORT
    assert (bug.title, bug.system_version) == (VALID["title"], VALID["system_version"])
    assert bug.component is None and bug.severity is None


def test_create_flushes_without_committing(session, initialized_db):
    bug = create_bug(session, BugCreate(**VALID))
    session.rollback()
    with session_factory(initialized_db)() as other:
        assert other.scalar(select(Bug.id).where(Bug.id == bug.id)) is None


def test_limits_are_inclusive(session):
    payload = {
        **VALID,
        "title": "t" * 120,
        "description": "d" * 5000,
        "reproduction_steps": "r" * 5000,
        "system_version": "v" * 50,
    }
    bug = get_bug(session, create_bug(session, BugCreate(**payload)).id)
    assert [len(bug.title), len(bug.description), len(bug.reproduction_steps)] == [120, 5000, 5000]
    assert len(bug.system_version) == 50


def test_rejected_input_stores_nothing(session):
    with pytest.raises(ValidationFailedError):
        BugCreate(**{**VALID, "title": "x" * 121})
    assert session.scalar(text("SELECT count(*) FROM bugs")) == 0


def test_get_returns_existing_bug(session):
    bug_id = make_bug(session)
    bug = get_bug(session, bug_id)
    assert bug.title == "Open bug" and bug.status is BugStatus.OPEN
    assert bug.component is None and bug.severity is None


def test_get_unknown_bug(session):
    with pytest.raises(NotFoundError) as caught:
        get_bug(session, 999999)
    assert caught.value.message == "Bug 999999 not found"


def test_update_changes_only_given_fields(session):
    bug_id = make_bug(session)
    before = get_bug(session, bug_id)
    after = update_bug(session, bug_id, BugUpdate(title="Renamed open bug"))
    assert after.title == "Renamed open bug"
    assert (
        after.model_copy(update={"title": before.title, "updated_at": before.updated_at}) == before
    )
    assert after.updated_at > before.updated_at
    assert after.status is BugStatus.OPEN


@pytest.mark.parametrize("status", ["processing", "processed", "failed"])
def test_update_of_non_open_bug_conflicts(session, status):
    bug_id = make_bug(session, status=status)
    with pytest.raises(StateConflictError) as caught:
        update_bug(session, bug_id, BugUpdate(title="Renamed"))
    assert caught.value.message == f"Bug {bug_id} is not open and cannot be edited"
    assert get_bug(session, bug_id).title == "Open bug"


def test_update_unknown_bug(session):
    with pytest.raises(NotFoundError) as caught:
        update_bug(session, 999999, BugUpdate(title="Renamed"))
    assert caught.value.message == "Bug 999999 not found"


def test_invalid_and_empty_updates_rejected_before_storage(session):
    bug_id = make_bug(session)
    with pytest.raises(ValidationFailedError) as caught:
        BugUpdate(title="x" * 121)
    assert caught.value.field_errors[0].field == "title"
    with pytest.raises(ValidationFailedError) as caught:
        BugUpdate()
    assert caught.value.field_errors[0].message == "at least one field is required"
    assert get_bug(session, bug_id).title == "Open bug"


def test_concurrent_claim_yields_conflict_not_lost_update(session, initialized_db):
    bug_id = make_bug(session)
    assert get_bug(session, bug_id).status is BugStatus.OPEN  # the caller saw it open
    with session_factory(initialized_db)() as claimer:
        claimer.execute(
            text("UPDATE bugs SET status = 'processing' WHERE id = :id"), {"id": bug_id}
        )
        claimer.commit()
    with pytest.raises(StateConflictError):
        update_bug(session, bug_id, BugUpdate(title="Lost update"))
    session.rollback()
    assert get_bug(session, bug_id).title == "Open bug"
