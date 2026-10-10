import pytest

from bugflow.services.reopen import reopen_bug
from tests_helpers import (
    RESULT_TABLES,
    bug_row,
    kept_snapshot,
    result_row_counts,
    result_rows,
    stored_status,
)

pytestmark = pytest.mark.integration


def test_processed_bug_is_reopened(initialized_db, triaged_bug):
    before = bug_row(initialized_db, triaged_bug)
    bug = reopen_bug(initialized_db, triaged_bug)
    assert bug.status == "open" and bug.component is None and bug.severity is None
    assert stored_status(initialized_db, triaged_bug) == "open"
    assert result_row_counts(initialized_db, triaged_bug) == dict.fromkeys(RESULT_TABLES, 0)
    assert bug_row(initialized_db, triaged_bug)[-1] > before[-1]


def test_history_and_embedding_are_kept(initialized_db, triaged_bug):
    before = kept_snapshot(initialized_db)
    assert len(before["runs"]) == 1 and len(before["run_steps"]) == 5
    assert len(before["run_logs"]) >= 3 and len(before["bug_embeddings"]) == 1
    reopen_bug(initialized_db, triaged_bug)
    assert kept_snapshot(initialized_db) == before


def test_other_bugs_are_not_affected(initialized_db, triaged_bug, neighbor_bug):
    rows = result_rows(initialized_db, neighbor_bug)
    kept = kept_snapshot(initialized_db, neighbor_bug)
    neighbor = bug_row(initialized_db, neighbor_bug)
    reopen_bug(initialized_db, triaged_bug)
    assert stored_status(initialized_db, neighbor_bug) == "processed"
    assert result_row_counts(initialized_db, neighbor_bug) == dict.fromkeys(RESULT_TABLES, 1)
    assert result_rows(initialized_db, neighbor_bug) == rows
    assert kept_snapshot(initialized_db, neighbor_bug) == kept
    assert bug_row(initialized_db, neighbor_bug) == neighbor


def test_failed_bug_is_reopened(initialized_db, failed_triaged_bug):
    kept = kept_snapshot(initialized_db)
    bug = reopen_bug(initialized_db, failed_triaged_bug)
    assert bug.status == "open"
    assert stored_status(initialized_db, failed_triaged_bug) == "open"
    assert kept_snapshot(initialized_db) == kept
