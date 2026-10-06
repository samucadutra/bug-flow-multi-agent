import pytest
from sqlalchemy import text

from bugflow.db.engine import session_factory
from bugflow.enums import RunStatus, RunType
from bugflow.logging_config import Redactor
from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.runs import RunRecorder, recorded_run

pytestmark = pytest.mark.integration


@pytest.fixture
def recorder(initialized_db, canary_api_key):
    return RunRecorder(session_factory(initialized_db), Redactor([canary_api_key]))


@pytest.fixture
def running(recorder):
    run_id = recorder.create_run(RunType.TRIAGE)
    recorder.start_run(run_id)
    return run_id


def test_create_run_is_queued(recorder, probe_bug):
    run = recorder.get_run(recorder.create_run(RunType.TRIAGE, bug_id=probe_bug))
    assert (run.status, run.type, run.bug_id) == (RunStatus.QUEUED, RunType.TRIAGE, probe_bug)
    assert (run.progress_done, run.progress_total) == (0, 0)
    assert run.started_at is not None and run.finished_at is None and run.error is None


def test_create_run_without_bug(recorder):
    assert recorder.get_run(recorder.create_run(RunType.SEED, total=5)).progress_total == 5


def test_start_progress_and_logs(recorder, running):
    assert recorder.get_run(running).status is RunStatus.RUNNING
    recorder.update_progress(running, 3, 20)
    run = recorder.get_run(running)
    assert (run.progress_done, run.progress_total) == (3, 20)
    recorder.update_progress(running, 4)
    assert recorder.get_run(running).progress_total == 20
    recorder.append_log(running, "INFO", "first")
    recorder.append_log(running, "WARNING", "second")
    logs = recorder.get_run_logs(running)
    assert [(entry.level, entry.message) for entry in logs] == [
        ("INFO", "first"),
        ("WARNING", "second"),
    ]
    assert all(entry.logged_at is not None for entry in logs)


def test_finish_succeeded_and_failed(recorder):
    ok = recorder.create_run(RunType.SEED)
    recorder.start_run(ok)
    recorder.finish_run(ok, RunStatus.SUCCEEDED)
    run = recorder.get_run(ok)
    assert run.status is RunStatus.SUCCEEDED and run.error is None
    assert run.finished_at is not None and run.finished_at >= run.started_at
    bad = recorder.create_run(RunType.SEED)
    recorder.finish_run(bad, RunStatus.FAILED, "boom")  # queued runs may fail before starting
    run = recorder.get_run(bad)
    assert (run.status, run.error) == (RunStatus.FAILED, "boom") and run.finished_at is not None


def test_illegal_transitions_raise(recorder, running):
    with pytest.raises(StateConflictError):
        recorder.start_run(running)
    with pytest.raises(ValueError):
        recorder.finish_run(running, RunStatus.RUNNING)
    recorder.finish_run(running, RunStatus.SUCCEEDED)
    for call in (
        lambda: recorder.finish_run(running, RunStatus.FAILED),
        lambda: recorder.start_run(running),
        lambda: recorder.update_progress(running, 1),
        lambda: recorder.append_log(running, "INFO", "late"),
    ):
        with pytest.raises(StateConflictError) as caught:
            call()
        assert caught.value.message == f"Run {running} is already finished"
    assert recorder.get_run(running).status is RunStatus.SUCCEEDED


def test_unknown_run(recorder):
    with pytest.raises(NotFoundError) as caught:
        recorder.finish_run(999999, RunStatus.SUCCEEDED)
    assert caught.value.message == "Run 999999 not found"
    with pytest.raises(NotFoundError):
        recorder.get_run(999999)
    with pytest.raises(NotFoundError):
        recorder.get_run_logs(999999)


def test_secrets_are_redacted(recorder, running, canary_api_key):
    recorder.append_log(running, "ERROR", f"key={canary_api_key}")
    recorder.finish_run(running, RunStatus.FAILED, f"failed with {canary_api_key}")
    assert recorder.get_run_logs(running)[0].message == "key=***"
    assert recorder.get_run(running).error == "failed with ***"


def test_writes_are_visible_to_other_connections(recorder, running, initialized_db):
    recorder.append_log(running, "INFO", "visible now")
    with initialized_db.connect() as other:
        rows = other.execute(
            text("SELECT message FROM run_logs WHERE run_id = :id"), {"id": running}
        ).all()
    assert [row[0] for row in rows] == ["visible now"]


def test_recorded_run_success(recorder, initialized_db):
    with recorded_run(recorder, RunType.SEED) as run:
        run.log("INFO", "working")
        run.progress(1, 1)
    with initialized_db.connect() as connection:
        rows = connection.execute(text("SELECT status, started_at, finished_at FROM runs")).all()
    assert len(rows) == 1 and rows[0][0] == "succeeded" and None not in rows[0]


def test_recorded_run_failure_propagates_and_records(recorder, initialized_db, canary_api_key):
    with pytest.raises(RuntimeError, match="kaput"):
        with recorded_run(recorder, RunType.SEED):
            raise RuntimeError("kaput")
    with pytest.raises(RuntimeError):
        with recorded_run(recorder, RunType.SEED):
            raise RuntimeError(f"leak {canary_api_key}")
    with initialized_db.connect() as connection:
        rows = connection.execute(text("SELECT status, error FROM runs ORDER BY id")).all()
    assert rows == [("failed", "kaput"), ("failed", "leak ***")]
