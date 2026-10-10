import pytest

from bugflow.services.recovery import recover_interrupted_runs
from tests_helpers import (
    add_bug,
    log_rows,
    result_row_counts,
    run_row,
    step_rows,
    stored_status,
)

pytestmark = pytest.mark.integration


def test_interrupted_runs_are_failed(initialized_db, interrupted_state):
    ids = interrupted_state
    result = recover_interrupted_runs(initialized_db)
    expected = {ids["crashed_run"], ids["queued_run"], ids["crashed_index_run"]}
    assert set(result.interrupted_run_ids) == expected
    for run_id in expected:
        row = run_row(initialized_db, run_id)
        assert (row.status, row.error) == ("failed", "interrupted")
        assert row.finished_at is not None


def test_their_bugs_return_to_failed(initialized_db, interrupted_state):
    ids = interrupted_state
    result = recover_interrupted_runs(initialized_db)
    for key in ("crashed_bug", "queued_bug", "orphan_bug"):
        assert stored_status(initialized_db, ids[key]) == "failed"
    assert set(result.recovered_bug_ids) == {
        ids["crashed_bug"],
        ids["queued_bug"],
        ids["orphan_bug"],
    }
    for key in ("crashed_bug", "queued_bug"):
        assert set(result_row_counts(initialized_db, ids[key]).values()) == {0}


def test_open_steps_are_closed(initialized_db, interrupted_state):
    run_id = interrupted_state["crashed_run"]
    recover_interrupted_runs(initialized_db)
    steps = step_rows(initialized_db, run_id)
    assert (steps[0].status, steps[0].output) == ("succeeded", {"ok": True})
    assert (steps[1].status, steps[1].error) == ("failed", "interrupted")
    assert [s.status for s in steps[2:]] == ["skipped"] * 3
    logs = log_rows(initialized_db, run_id)
    assert len(logs) == 3 and logs[2].level == "ERROR"


def test_finished_work_is_untouched(initialized_db, interrupted_state):
    ids = interrupted_state
    result = recover_interrupted_runs(initialized_db)
    row = run_row(initialized_db, ids["finished_run"])
    assert (row.status, row.error) == ("succeeded", None)
    assert stored_status(initialized_db, ids["finished_bug"]) == "processed"
    assert set(result_row_counts(initialized_db, ids["finished_bug"]).values()) == {1}
    assert ids["finished_run"] not in result.interrupted_run_ids
    assert ids["finished_bug"] not in result.recovered_bug_ids


def test_recovery_is_repeatable(initialized_db, interrupted_state):
    recover_interrupted_runs(initialized_db)
    again = recover_interrupted_runs(initialized_db)
    assert again.interrupted_run_ids == [] and again.recovered_bug_ids == []
    assert len(log_rows(initialized_db, interrupted_state["crashed_run"])) == 3
    assert run_row(initialized_db, interrupted_state["crashed_run"]).error == "interrupted"


def test_a_recovered_bug_can_be_triaged_again(initialized_db, interrupted_state, runner):
    recover_interrupted_runs(initialized_db)
    bug_id = interrupted_state["crashed_bug"]
    result = runner.start_run("triage", {"bug_id": bug_id})
    assert result.run_id != interrupted_state["crashed_run"]
    assert stored_status(initialized_db, bug_id) in ("processing", "processed")
    assert runner.wait_idle(60)


def test_an_empty_database_returns_empty_lists(initialized_db):
    result = recover_interrupted_runs(initialized_db)
    assert result.interrupted_run_ids == [] and result.recovered_bug_ids == []


def test_no_runs_table_returns_empty_lists(fresh_schema):
    result = recover_interrupted_runs(fresh_schema)
    assert result.interrupted_run_ids == [] and result.recovered_bug_ids == []


def test_a_bug_with_a_finished_run_is_not_touched_but_processing_is_freed(initialized_db):
    bug_id = add_bug(initialized_db, status="processing")
    recover_interrupted_runs(initialized_db)
    assert stored_status(initialized_db, bug_id) == "failed"
