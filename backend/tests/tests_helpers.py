"""Small helpers shared by integration tests."""

from __future__ import annotations

from sqlalchemy import Engine

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
