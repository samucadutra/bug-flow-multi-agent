import threading
import time

import pytest

from bugflow.db.engine import session_factory
from bugflow.services.errors import NotFoundError, ValidationFailedError
from bugflow.services.recovery import recover_interrupted_runs
from bugflow.services.run_events import iter_run_events, read_run_events
from bugflow.services.runs import RunRecorder

pytestmark = pytest.mark.integration

MESSAGES = [
    "AG1 Component Classifier started",
    "AG1 Component Classifier succeeded in 1200 ms",
    "AG2 Severity Classifier started",
]


def test_full_read_of_a_run_in_progress(initialized_db, streaming_state):
    page = read_run_events(initialized_db, streaming_state["run_id"])
    types = [e.type for e in page.events]
    assert types == ["step"] * 5 + ["log"] * 3 + ["run"]
    steps = [e.step for e in page.events if e.type == "step"]
    assert [s.position for s in steps] == [1, 2, 3, 4, 5]
    assert [s.status.value for s in steps] == [
        "succeeded",
        "running",
        "pending",
        "pending",
        "pending",
    ]
    logs = [e.log for e in page.events if e.type == "log"]
    assert [log.message for log in logs] == MESSAGES and {log.level for log in logs} == {"INFO"}
    run = page.events[-1].run
    assert (run.status.value, run.progress_done, run.progress_total) == ("running", 1, 5)
    assert page.finished is False
    assert page.cursor == page.events[-1].cursor


def test_resume_after_a_cursor_with_new_rows(initialized_db, streaming_state):
    run_id = streaming_state["run_id"]
    cursor = read_run_events(initialized_db, run_id).cursor
    recorder = RunRecorder(session_factory(initialized_db))
    recorder.finish_step(run_id, 2, "succeeded", output={"ok": 1}, duration_ms=800)
    recorder.append_log(run_id, "INFO", "AG2 Severity Classifier succeeded in 800 ms")
    recorder.append_log(run_id, "INFO", "AG3 Technical Analyst started")
    page = read_run_events(initialized_db, run_id, cursor)
    assert [e.type for e in page.events] == ["step", "log", "log"]
    assert page.events[0].step.position == 2 and page.events[0].step.status.value == "succeeded"
    assert [e.log.message for e in page.events[1:]] == [
        "AG2 Severity Classifier succeeded in 800 ms",
        "AG3 Technical Analyst started",
    ]


def test_nothing_new_returns_the_same_cursor(initialized_db, streaming_state):
    run_id = streaming_state["run_id"]
    cursor = read_run_events(initialized_db, run_id).cursor
    page = read_run_events(initialized_db, run_id, cursor)
    assert page.events == [] and page.cursor == cursor and page.finished is False


def test_a_finished_run_ends_with_the_run_event(initialized_db, interrupted_state):
    page = read_run_events(initialized_db, interrupted_state["finished_run"])
    assert [e.step.status.value for e in page.events if e.type == "step"] == ["succeeded"] * 5
    assert len([e for e in page.events if e.type == "log"]) >= 5
    last = page.events[-1]
    assert last.type == "run" and last.run.status.value == "succeeded"
    assert (last.run.progress_done, last.run.progress_total) == (5, 5)
    assert last.run.finished_at is not None and page.finished is True


def test_events_of_other_runs_are_excluded(initialized_db, streaming_state):
    other = RunRecorder(session_factory(initialized_db))
    other_id = other.create_run("seed")
    other.append_log(other_id, "INFO", "other run line")
    page = read_run_events(initialized_db, streaming_state["run_id"])
    assert all(e.log.run_id == streaming_state["run_id"] for e in page.events if e.type == "log")


def test_the_iterator_follows_a_run_finished_by_another_connection(initialized_db, streaming_state):
    run_id = streaming_state["run_id"]
    recorder = RunRecorder(session_factory(initialized_db))
    start = time.monotonic()

    def finish():
        time.sleep(1.2)
        recorder.append_log(run_id, "INFO", "AG2 Severity Classifier succeeded in 800 ms")
        recorder.finish_run(run_id, "succeeded")

    thread = threading.Thread(target=finish)
    thread.start()
    arrivals = [(time.monotonic() - start, e) for e in iter_run_events(initialized_db, run_id)]
    thread.join()
    first_nine = [t for t, _ in arrivals[:9]]
    assert max(first_nine) < 1.0
    rest = arrivals[9:]
    assert [e.type for _, e in rest] == ["log", "run"]
    assert arrivals[-1][1].type == "run" and arrivals[-1][1].run.status.value == "succeeded"
    assert rest[0][0] < 1.2 + 1.0


def test_unknown_run_and_malformed_cursor(initialized_db, streaming_state):
    with pytest.raises(NotFoundError, match="^Run 999999 not found$"):
        iter_run_events(initialized_db, 999999)
    with pytest.raises(ValidationFailedError) as caught:
        read_run_events(initialized_db, streaming_state["run_id"], "not-a-cursor")
    assert [(e.field, e.message) for e in caught.value.field_errors] == [
        ("after", "invalid cursor")
    ]


def test_steps_closed_by_recovery_appear_as_failed_and_skipped(initialized_db, streaming_state):
    run_id = streaming_state["run_id"]
    cursor = read_run_events(initialized_db, run_id).cursor
    recover_interrupted_runs(initialized_db)
    page = read_run_events(initialized_db, run_id, cursor)
    changed = {e.step.position: e.step.status.value for e in page.events if e.type == "step"}
    assert changed == {2: "failed", 3: "skipped", 4: "skipped", 5: "skipped"}
    assert page.events[-1].type == "run" and page.events[-1].run.status.value == "failed"
    assert page.finished is True


def test_a_run_without_steps_or_logs(initialized_db):
    run_id = RunRecorder(session_factory(initialized_db)).create_run("index")
    page = read_run_events(initialized_db, run_id)
    assert [e.type for e in page.events] == ["run"] and page.finished is False
