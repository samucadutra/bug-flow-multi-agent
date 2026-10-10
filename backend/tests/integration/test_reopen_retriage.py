import pytest
from sqlalchemy import text

from bugflow.services.reopen import reopen_bug
from bugflow.services.triage import triage_bug
from tests_helpers import RESULT_TABLES, kept_snapshot, result_row_counts

pytestmark = pytest.mark.integration


def test_reopened_bug_is_triaged_again(initialized_db, triaged_bug, get_client, stand_in):
    before = kept_snapshot(initialized_db, triaged_bug)
    old_run = before["runs"][0][0]
    reopen_bug(initialized_db, triaged_bug)
    outcome = triage_bug(initialized_db, get_client, triaged_bug)
    assert outcome.status == "processed" and outcome.error is None
    assert result_row_counts(initialized_db, triaged_bug) == dict.fromkeys(RESULT_TABLES, 1)
    assert outcome.run_id != old_run
    with initialized_db.connect() as connection:
        for table in RESULT_TABLES:
            run_ids = connection.execute(
                text(f"SELECT run_id FROM {table} WHERE bug_id = :id"),  # noqa: S608
                {"id": triaged_bug},
            ).scalars()
            assert set(run_ids) == {outcome.run_id}
        count = connection.execute(
            text("SELECT count(*) FROM runs WHERE bug_id = :id AND type = 'triage'"),
            {"id": triaged_bug},
        ).scalar_one()
    assert count == 2
    after = kept_snapshot(initialized_db, triaged_bug)
    assert after["runs"][0] == before["runs"][0]
    assert after["run_steps"][:5] == before["run_steps"]
