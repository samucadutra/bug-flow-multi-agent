from datetime import UTC, datetime

import pytest

from bugflow.enums import RunStatus, RunType
from bugflow.logging_config import Redactor
from bugflow.services.runs import DeferredRunRecorder


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def add(self, obj):
        self.added.append(obj)
        obj.id = 42

    def add_all(self, objs):
        self.added.extend(objs)

    def flush(self):
        pass

    def commit(self):
        self.committed = True


def test_lines_keep_order_and_timestamps():
    recorder = DeferredRunRecorder(RunType.INIT)
    recorder.append_log("INFO", "first")
    recorder.append_log("warning", "second")
    assert [(line.level, line.message) for line in recorder.lines] == [
        ("INFO", "first"),
        ("WARNING", "second"),
    ]
    assert recorder.lines[0].logged_at <= recorder.lines[1].logged_at


def test_persist_carries_original_start_and_lines():
    recorder = DeferredRunRecorder(RunType.RESET)
    started = recorder.started_at
    recorder.append_log("INFO", "line")
    recorder.update_progress(1, 2)
    session = FakeSession()
    run_id = recorder.persist(lambda: session, RunStatus.SUCCEEDED)
    run, log = session.added
    assert run_id == 42 and session.committed
    assert run.started_at == started and run.finished_at >= started
    assert (run.type, run.status, run.progress_done, run.progress_total) == (
        "reset",
        "succeeded",
        1,
        2,
    )
    assert log.logged_at == recorder.lines[0].logged_at and log.run_id == 42
    assert isinstance(run.finished_at, datetime) and run.finished_at.tzinfo is UTC


def test_failure_status_carries_redacted_error(canary_api_key):
    recorder = DeferredRunRecorder(RunType.INIT, Redactor([canary_api_key]))
    recorder.append_log("ERROR", f"key {canary_api_key}")
    session = FakeSession()
    error = recorder.error_text(RuntimeError(f"bad {canary_api_key}"))
    recorder.persist(lambda: session, RunStatus.FAILED, error)
    run, log = session.added
    assert run.error == "bad ***" and log.message == "key ***"


def test_non_final_status_rejected():
    with pytest.raises(ValueError):
        DeferredRunRecorder(RunType.INIT).persist(lambda: FakeSession(), RunStatus.RUNNING)


def test_unknown_level_rejected():
    with pytest.raises(ValueError):
        DeferredRunRecorder(RunType.INIT).append_log("LOUD", "x")
