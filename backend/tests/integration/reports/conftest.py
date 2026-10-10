"""Fixtures for the report integration tests: the processed-bug handles and a probing hook."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from bugflow.db.engine import session_factory
from report_helpers import HOSTILE_OVERRIDES, add_processed_bug
from tests_helpers import add_bug


def add_similar_bug(engine) -> int:
    """Handle `similar-bug`: `open`, titled "Payment form freezes on Safari 17"."""
    return add_bug(engine, title="Payment form freezes on Safari 17")


@pytest.fixture
def report_bug(initialized_db):
    """Handle `report-bug` with `similar-bug` referenced; returns (bug id, similar bug id)."""
    similar = add_similar_bug(initialized_db)
    return add_processed_bug(initialized_db, similar_ids=[similar]), similar


@pytest.fixture
def stored_report_bug(initialized_db):
    return add_processed_bug(
        initialized_db,
        stored_markdown="# Stored report\n",
        stored_html="<p>Stored report</p>\n",
    )


@pytest.fixture
def hostile_bug(initialized_db):
    overrides = dict(HOSTILE_OVERRIDES)
    bug = {key: overrides.pop(key) for key in ("title", "description", "reproduction_steps")}
    return add_processed_bug(initialized_db, bug=bug, **overrides)


@pytest.fixture
def unprocessed_bug(initialized_db):
    return add_bug(initialized_db)


class ProbingHook:
    """Records, from inside the result transaction, what a later hook can see."""

    def __init__(self) -> None:
        self.runs = 0
        self.markdown_present: bool | None = None
        self.html_present: bool | None = None
        self.status: str | None = None

    def __call__(self, session, bug_id, results) -> None:
        self.runs += 1
        row = session.execute(
            text("SELECT markdown IS NOT NULL, html IS NOT NULL FROM bug_reports WHERE bug_id=:i"),
            {"i": bug_id},
        ).one()
        self.markdown_present, self.html_present = row
        self.status = session.execute(
            text("SELECT status FROM bugs WHERE id = :i"), {"i": bug_id}
        ).scalar_one()


@pytest.fixture
def probing_hook() -> ProbingHook:
    return ProbingHook()


@pytest.fixture
def db_session(initialized_db):
    with session_factory(initialized_db)() as session:
        yield session
