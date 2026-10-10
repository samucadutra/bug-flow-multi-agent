"""The report hook inside the triage transaction, with the OpenAI stand-in."""

from __future__ import annotations

import re
from datetime import timedelta

import pytest
from sqlalchemy import text

from bugflow.enums import BugStatus
from bugflow.services.reports import install_report_hook
from bugflow.services.triage import register_result_hook, triage_bug
from report_helpers import stored_texts
from tests_helpers import RESULT_TABLES, result_row_counts, stored_status

pytestmark = pytest.mark.integration


def test_a_triaged_bug_has_a_stored_report(initialized_db, open_bug, get_client) -> None:
    install_report_hook()
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.processed and outcome.error is None
    markdown, html = stored_texts(initialized_db, open_bug)
    assert markdown and html
    assert markdown.split("\n")[0] == "# Checkout button does nothing on Safari 17"


def test_the_report_is_written_inside_the_result_transaction(
    initialized_db, open_bug, get_client, probing_hook
) -> None:
    install_report_hook()
    register_result_hook(probing_hook)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.processed
    assert probing_hook.runs == 1
    assert (probing_hook.markdown_present, probing_hook.html_present) == (True, True)
    assert probing_hook.status == "processing"
    assert stored_status(initialized_db, open_bug) == "processed"


def test_a_rendering_failure_rolls_everything_back(initialized_db, open_bug, get_client) -> None:
    def failing(data):
        raise RuntimeError("forced render failure")

    install_report_hook(render=failing)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.status == BugStatus.FAILED
    assert outcome.error == "Result hook failed: Report rendering failed: forced render failure"
    assert stored_status(initialized_db, open_bug) == "failed"
    assert result_row_counts(initialized_db, open_bug) == dict.fromkeys(RESULT_TABLES, 0)
    with initialized_db.connect() as connection:
        steps = connection.execute(text("SELECT status FROM run_steps ORDER BY position")).all()
        run = connection.execute(text("SELECT status FROM runs")).scalar_one()
    assert steps == [("succeeded",)] * 5 and run == "failed"


def test_the_stored_deadline_follows_the_stored_completion_time(
    initialized_db, open_bug, get_client
) -> None:
    install_report_hook()
    assert triage_bug(initialized_db, get_client, open_bug).processed
    markdown, _ = stored_texts(initialized_db, open_bug)
    with initialized_db.connect() as connection:
        created = connection.execute(
            text("SELECT (created_at AT TIME ZONE 'UTC')::date FROM bug_reports")
        ).scalar_one()
    assert f"| Report completed | {created.isoformat()} |" in markdown
    deadline = created + timedelta(days=5)
    assert re.search(rf"^\| Deadline \| {deadline.isoformat()} \|$", markdown, re.M)
