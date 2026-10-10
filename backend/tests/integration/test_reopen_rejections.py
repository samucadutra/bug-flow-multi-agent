import pytest

from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.reopen import reopen_bug
from tests_helpers import bug_row, kept_snapshot

pytestmark = pytest.mark.integration


def test_processing_bug_is_rejected(initialized_db, busy_bug):
    row, kept = bug_row(initialized_db, busy_bug), kept_snapshot(initialized_db)
    with pytest.raises(StateConflictError) as caught:
        reopen_bug(initialized_db, busy_bug)
    assert caught.value.message == f"Bug {busy_bug} is being processed and cannot be reopened"
    assert bug_row(initialized_db, busy_bug) == row
    assert kept_snapshot(initialized_db) == kept


def test_open_bug_is_rejected(initialized_db, untriaged_bug):
    row = bug_row(initialized_db, untriaged_bug)
    with pytest.raises(StateConflictError) as caught:
        reopen_bug(initialized_db, untriaged_bug)
    assert caught.value.message == f"Bug {untriaged_bug} is already open"
    assert bug_row(initialized_db, untriaged_bug) == row
    assert kept_snapshot(initialized_db)["runs"] == []


def test_unknown_bug(initialized_db):
    with pytest.raises(NotFoundError) as caught:
        reopen_bug(initialized_db, 999999)
    assert caught.value.message == "Bug 999999 not found"
