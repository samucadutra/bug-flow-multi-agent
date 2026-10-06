import pytest

from bugflow.db.engine import session_factory
from mocks.fake_openai_server import default_reply
from tests_helpers import (
    result_row_counts,
    run_row,
    step_rows,
    stored_status,
    wait_final,
    wait_until,
)

pytestmark = pytest.mark.integration


def test_a_started_triage_completes_in_the_background(runner, initialized_db, open_bug):
    run_id = runner.start_run("triage", {"bug_id": open_bug}).run_id
    row = wait_final(initialized_db, run_id)
    assert (row.status, row.error, row.progress_done, row.progress_total) == (
        "succeeded",
        None,
        5,
        5,
    )
    assert stored_status(initialized_db, open_bug) == "processed"
    assert set(result_row_counts(initialized_db, open_bug).values()) == {1}
    assert [s.status for s in step_rows(initialized_db, run_id)] == ["succeeded"] * 5


def test_status_and_progress_move_forward(runner, initialized_db, open_bug, stand_in):
    stand_in.script_chat(
        [{"role": "Severity Classifier", "json": default_reply("Severity Classifier"), "delay": 2}]
    )
    run_id = runner.start_run("triage", {"bug_id": open_bug}).run_id
    observed = []

    def poll():
        row = run_row(initialized_db, run_id)
        observed.append((row.status, row.progress_done, stored_status(initialized_db, open_bug)))
        return row.status in ("succeeded", "failed")

    wait_until(poll, 60, 0.1)
    statuses = []
    for status, _, _ in observed:
        if not statuses or statuses[-1] != status:
            statuses.append(status)
    order = ["queued", "running", "succeeded"]
    assert [order.index(s) for s in statuses] == sorted(order.index(s) for s in statuses)
    assert statuses[-1] == "succeeded" and "running" in statuses
    progress = [p for _, p, _ in observed]
    assert progress == sorted(progress) and progress[-1] == 5
    assert all(bug == "processing" for status, _, bug in observed if status != "succeeded")


def test_an_agent_failure_ends_the_run_as_failed(runner, initialized_db, open_bug, stand_in):
    wrong = default_reply("Severity Classifier")
    wrong["severity"] = "high"
    stand_in.script_chat([{"role": "Severity Classifier", "json": wrong, "repeat": 2}])
    run_id = runner.start_run("triage", {"bug_id": open_bug}).run_id
    row = wait_final(initialized_db, run_id)
    assert (row.status, row.error) == ("failed", "AG2 returned invalid severity 'high'")
    assert stored_status(initialized_db, open_bug) == "failed"
    assert set(result_row_counts(initialized_db, open_bug).values()) == {0}
    assert [s.status for s in step_rows(initialized_db, run_id)] == [
        "succeeded",
        "failed",
        "skipped",
        "skipped",
        "skipped",
    ]


def test_an_unexpected_error_does_not_stop_the_runner(
    make_runner, boom_factory, initialized_db, three_open_bugs
):
    runner = make_runner(boom_factory)
    one, two, three = (
        runner.start_run("triage", {"bug_id": bug}).run_id for bug in three_open_bugs
    )
    assert runner.wait_idle(120)
    first = run_row(initialized_db, one)
    assert first.status == "failed" and first.error
    assert stored_status(initialized_db, three_open_bugs[0]) == "failed"
    assert {s.status for s in step_rows(initialized_db, one)} <= {"failed", "skipped", "succeeded"}
    for run_id, bug in ((two, three_open_bugs[1]), (three, three_open_bugs[2])):
        assert run_row(initialized_db, run_id).status == "succeeded"
        assert stored_status(initialized_db, bug) == "processed"


def test_the_safety_net_handles_an_error_after_the_run_started(
    make_runner, initialized_db, open_bug, monkeypatch
):
    from bugflow.services import background

    def explode(*args, **kwargs):
        raise RuntimeError("sk-test-canary-1234567890abcdef leaked")

    monkeypatch.setattr(background, "execute_triage", explode)
    runner = make_runner()
    run_id = runner.start_run("triage", {"bug_id": open_bug}).run_id
    assert runner.wait_idle(30)
    row = run_row(initialized_db, run_id)
    assert row.status == "failed" and "sk-test-canary" not in row.error
    assert stored_status(initialized_db, open_bug) == "failed"
    assert session_factory
