"""Small helpers shared by integration tests."""

from __future__ import annotations

from sqlalchemy import Engine, text

from bugflow.db.engine import session_factory
from bugflow.db.models import Bug


def add_numbered(engine: Engine, count: int) -> list[int]:
    """Bugs titled "Batchbug 01" ... with valid values for every column."""
    with session_factory(engine)() as db_session:
        bugs = [
            Bug(
                title=f"Batchbug {number:02d}",
                description=f"Description of batch bug {number}.",
                reproduction_steps="1. Open the page.",
                system_version="web 1.0.0",
                environment="testing",
                reporting_team="qa",
            )
            for number in range(1, count + 1)
        ]
        db_session.add_all(bugs)
        db_session.commit()
        return [bug.id for bug in bugs]


OPEN_BUG_FIELDS = {
    "title": "Checkout button does nothing on Safari 17",
    "description": "Clicking Place order shows no response and no network call.",
    "reproduction_steps": "Add an item, go to checkout in Safari 17, click the button.",
    "system_version": "web 3.8.2",
    "environment": "production",
    "reporting_team": "support",
}
RESULT_TABLES = (
    "component_classifications",
    "severity_classifications",
    "technical_analyses",
    "resolution_plans",
    "bug_reports",
)


def add_bug(engine: Engine, status: str = "open", **overrides: str) -> int:
    fields = {**OPEN_BUG_FIELDS, **overrides}
    with session_factory(engine)() as db_session:
        bug = Bug(status=status, **fields)
        db_session.add(bug)
        db_session.commit()
        return bug.id


def result_row_counts(engine: Engine, bug_id: int) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE bug_id = :id"),  # noqa: S608
                {"id": bug_id},
            ).scalar_one()
            for table in RESULT_TABLES
        }


def stored_status(engine: Engine, bug_id: int) -> str:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT status FROM bugs WHERE id = :id"), {"id": bug_id}
        ).scalar_one()
