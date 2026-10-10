import time

import pytest
from sqlalchemy import text

from mocks.fake_openai_server import default_reply
from tests_helpers import run_row, run_rows, step_rows, stored_status

pytestmark = pytest.mark.integration


def wrong_severity(stand_in, contains):
    wrong = default_reply("Severity Classifier")
    wrong["severity"] = "high"
    stand_in.script_chat(
        [{"role": "Severity Classifier", "contains": contains, "json": wrong, "repeat": 2}]
    )


def test_a_failure_does_not_stop_the_batch(runner, initialized_db, three_open_bugs, stand_in):
    wrong_severity(stand_in, "Bug two")
    runner.start_run("triage", {"all": True})
    assert runner.wait_idle(120)
    runs = run_rows(initialized_db, "type = 'triage'")
    assert [r.status for r in runs] == ["succeeded", "failed", "succeeded"]
    assert [stored_status(initialized_db, b) for b in three_open_bugs] == [
        "processed",
        "failed",
        "processed",
    ]
    assert runs[1].error == "AG2 returned invalid severity 'high'"
    with initialized_db.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM bugs WHERE status='processing'")).scalar()
            == 0
        )


def test_queued_runs_wait_for_the_running_one(runner, initialized_db, three_open_bugs, stand_in):
    stand_in.script_chat(
        [
            {
                "role": "Component Classifier",
                "json": default_reply("Component Classifier"),
                "delay": 3,
            }
        ]
    )
    result = runner.start_run("triage", {"all": True})
    time.sleep(1.5)
    first, second, third = result.run_ids
    assert run_row(initialized_db, first).status == "running"
    for run_id in (second, third):
        assert run_row(initialized_db, run_id).status == "queued"
        assert step_rows(initialized_db, run_id) == []
    assert [stored_status(initialized_db, b) for b in three_open_bugs] == ["processing"] * 3
    assert runner.wait_idle(120)


def test_runs_execute_one_at_a_time(runner, initialized_db, three_open_bugs, stand_in):
    runner.start_run("triage", {"all": True})
    assert runner.wait_idle(120)
    runs = run_rows(initialized_db)
    for current, following in zip(runs, runs[1:], strict=False):
        assert current.finished_at <= step_rows(initialized_db, following.id)[0].started_at
    requests = [r for r in stand_in.chat_requests() if r.get("messages") is not None]
    texts = [str(r["messages"]) for r in requests]
    last_one = max(i for i, t in enumerate(texts) if "Title: Bug one" in t)
    first_two = min(i for i, t in enumerate(texts) if "Title: Bug two" in t)
    assert last_one < first_two


def test_separate_starts_are_queued_in_order(runner, initialized_db, three_open_bugs, stand_in):
    stand_in.script_chat(
        [
            {
                "role": "Component Classifier",
                "contains": "Bug one",
                "json": default_reply("Component Classifier"),
                "delay": 3,
            }
        ]
    )
    one = runner.start_run("triage", {"bug_id": three_open_bugs[0]}).run_id
    started = time.monotonic()
    two = runner.start_run("triage", {"bug_id": three_open_bugs[1]}).run_id
    assert time.monotonic() - started < 1
    time.sleep(1.5)
    assert run_row(initialized_db, one).status == "running"
    assert run_row(initialized_db, two).status == "queued"
    assert runner.wait_idle(120)
    assert run_row(initialized_db, two).status == "succeeded"
    assert run_row(initialized_db, one).finished_at <= step_rows(initialized_db, two)[0].started_at


def test_wait_idle_semantics(runner, initialized_db, open_bug, stand_in):
    assert runner.wait_idle(0.1) is True
    stand_in.script_chat(
        [
            {
                "role": "Component Classifier",
                "json": default_reply("Component Classifier"),
                "delay": 2,
            }
        ]
    )
    runner.start_run("triage", {"bug_id": open_bug})
    assert runner.wait_idle(0.2) is False
    assert runner.wait_idle(60) is True
