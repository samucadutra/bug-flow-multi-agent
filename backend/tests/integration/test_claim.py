import threading

import pytest
from sqlalchemy import text

from bugflow.db.engine import session_factory
from bugflow.enums import BugStatus
from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.triage import claim_bug
from tests_helpers import add_bug, stored_status

pytestmark = pytest.mark.integration


def run_count(engine):
    with engine.connect() as connection:
        return connection.execute(text("SELECT count(*) FROM runs")).scalar_one()


def test_open_bug_is_claimed(initialized_db, open_bug):
    claimed = claim_bug(initialized_db, open_bug)
    assert claimed.id == open_bug and claimed.status == BugStatus.PROCESSING
    assert stored_status(initialized_db, open_bug) == "processing"
    assert run_count(initialized_db) == 0


def test_failed_bug_is_claimed(initialized_db):
    bug_id = add_bug(initialized_db, status="failed")
    assert claim_bug(initialized_db, bug_id).status == BugStatus.PROCESSING


def test_claim_refreshes_updated_at(initialized_db, open_bug):
    with initialized_db.connect() as connection:
        before = connection.execute(text("SELECT updated_at FROM bugs")).scalar_one()
    claimed = claim_bug(initialized_db, open_bug)
    assert claimed.updated_at > before


def test_processing_bug_is_refused(initialized_db):
    bug_id = add_bug(initialized_db, status="processing")
    with pytest.raises(StateConflictError) as caught:
        claim_bug(initialized_db, bug_id)
    assert caught.value.message == f"Bug {bug_id} is already being processed"
    assert stored_status(initialized_db, bug_id) == "processing"
    assert run_count(initialized_db) == 0


def test_processed_bug_is_refused(initialized_db):
    bug_id = add_bug(initialized_db, status="processed")
    with pytest.raises(StateConflictError) as caught:
        claim_bug(initialized_db, bug_id)
    assert caught.value.message == f"Bug {bug_id} has already been processed; reopen it first"
    assert stored_status(initialized_db, bug_id) == "processed"


def test_unknown_bug(initialized_db):
    with pytest.raises(NotFoundError) as caught:
        claim_bug(initialized_db, 999999)
    assert caught.value.message == "Bug 999999 not found"


def test_concurrent_claims_have_one_winner(initialized_db, open_bug):
    barrier = threading.Barrier(2)
    results = []

    def attempt():
        barrier.wait()
        try:
            results.append(claim_bug(initialized_db, open_bug))
        except StateConflictError as exc:
            results.append(exc)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    winners = [r for r in results if not isinstance(r, Exception)]
    losers = [r for r in results if isinstance(r, StateConflictError)]
    assert len(winners) == 1 and len(losers) == 1
    assert winners[0].status == BugStatus.PROCESSING
    assert stored_status(initialized_db, open_bug) == "processing"


def test_claim_does_not_touch_other_bugs(initialized_db, open_bug):
    other = add_bug(initialized_db, title="Other")
    claim_bug(initialized_db, open_bug)
    assert stored_status(initialized_db, other) == "open"
    assert session_factory(initialized_db)
