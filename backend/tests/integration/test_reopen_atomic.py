import pytest
from sqlalchemy import text

from bugflow.services.reopen import (
    ReopenFailedError,
    register_reopen_hook,
    reopen_bug,
)
from tests_helpers import RESULT_TABLES, bug_row, kept_snapshot, result_row_counts, result_rows

pytestmark = pytest.mark.integration


def test_failing_hook_rolls_everything_back(initialized_db, triaged_bug, failing_reopen_hook):
    row, rows = bug_row(initialized_db, triaged_bug), result_rows(initialized_db, triaged_bug)
    kept = kept_snapshot(initialized_db)
    register_reopen_hook(failing_reopen_hook)
    with pytest.raises(ReopenFailedError) as caught:
        reopen_bug(initialized_db, triaged_bug)
    assert caught.value.message == f"Reopen of bug {triaged_bug} failed; nothing was changed"
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert bug_row(initialized_db, triaged_bug) == row
    assert result_rows(initialized_db, triaged_bug) == rows
    assert kept_snapshot(initialized_db) == kept


def test_changes_are_one_transaction(initialized_db, triaged_bug, recording_reopen_hook):
    register_reopen_hook(recording_reopen_hook)
    reopen_bug(initialized_db, triaged_bug)
    zeros, ones = dict.fromkeys(RESULT_TABLES, 0), dict.fromkeys(RESULT_TABLES, 1)
    assert recording_reopen_hook.runs == 1
    assert recording_reopen_hook.inside == {"status": "open", "counts": zeros}
    assert recording_reopen_hook.separate == {"status": "processed", "counts": ones}
    with initialized_db.connect() as connection:
        status = connection.execute(
            text("SELECT status FROM bugs WHERE id = :id"), {"id": triaged_bug}
        ).scalar_one()
    assert status == "open"
    assert result_row_counts(initialized_db, triaged_bug) == zeros


def test_failed_bug_is_restored_on_failure(initialized_db, failed_triaged_bug, failing_reopen_hook):
    row, kept = bug_row(initialized_db, failed_triaged_bug), kept_snapshot(initialized_db)
    register_reopen_hook(failing_reopen_hook)
    with pytest.raises(ReopenFailedError) as caught:
        reopen_bug(initialized_db, failed_triaged_bug)
    assert caught.value.message == f"Reopen of bug {failed_triaged_bug} failed; nothing was changed"
    assert bug_row(initialized_db, failed_triaged_bug) == row
    assert kept_snapshot(initialized_db) == kept


def test_hooks_run_in_registration_order(initialized_db, triaged_bug):
    order = []
    register_reopen_hook(lambda session, bug_id: order.append("first"))
    register_reopen_hook(lambda session, bug_id: order.append("second"))
    reopen_bug(initialized_db, triaged_bug)
    assert order == ["first", "second"]


def test_database_error_in_a_hook_is_rolled_back(initialized_db, triaged_bug):
    row, rows = bug_row(initialized_db, triaged_bug), result_rows(initialized_db, triaged_bug)

    def broken(session, bug_id):
        session.execute(text("SELECT * FROM no_such_table"))

    register_reopen_hook(broken)
    with pytest.raises(ReopenFailedError):
        reopen_bug(initialized_db, triaged_bug)
    assert bug_row(initialized_db, triaged_bug) == row
    assert result_rows(initialized_db, triaged_bug) == rows
