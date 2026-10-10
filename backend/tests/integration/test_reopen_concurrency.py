import threading

import pytest

from bugflow.services.errors import StateConflictError
from bugflow.services.reopen import reopen_bug
from tests_helpers import RESULT_TABLES, result_row_counts, stored_status

pytestmark = pytest.mark.integration


def test_simultaneous_reopens_have_one_winner(initialized_db, triaged_bug):
    barrier = threading.Barrier(2)
    outcomes = []

    def worker():
        barrier.wait()
        try:
            outcomes.append(reopen_bug(initialized_db, triaged_bug))
        except StateConflictError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    winners = [o for o in outcomes if not isinstance(o, Exception)]
    losers = [o for o in outcomes if isinstance(o, StateConflictError)]
    assert len(winners) == 1 and winners[0].status == "open"
    assert [e.message for e in losers] == [f"Bug {triaged_bug} is already open"]
    assert stored_status(initialized_db, triaged_bug) == "open"
    assert result_row_counts(initialized_db, triaged_bug) == dict.fromkeys(RESULT_TABLES, 0)
