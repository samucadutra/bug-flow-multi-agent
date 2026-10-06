import pytest
from sqlalchemy import text

from bugflow.db.engine import session_factory
from bugflow.enums import RunStatus, RunType, StepStatus
from bugflow.logging_config import Redactor
from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.runs import RunRecorder

pytestmark = pytest.mark.integration

KEYS = ["a", "b", "c"]


@pytest.fixture
def recorder(initialized_db):
    return RunRecorder(session_factory(initialized_db), Redactor(["s3cret-value"]))


@pytest.fixture
def run_id(recorder):
    run = recorder.create_run(RunType.TRIAGE, None, 3)
    recorder.start_run(run)
    return run


def test_create_steps_inserts_pending_steps_in_order(recorder, run_id):
    recorder.create_steps(run_id, KEYS)
    steps = recorder.get_steps(run_id)
    assert [(s.position, s.agent_key, s.status) for s in steps] == [
        (1, "a", StepStatus.PENDING),
        (2, "b", StepStatus.PENDING),
        (3, "c", StepStatus.PENDING),
    ]
    assert all(s.input is None and s.output is None and s.started_at is None for s in steps)


def test_step_lifecycle_is_visible_to_other_connections(recorder, run_id, initialized_db):
    recorder.create_steps(run_id, KEYS)
    recorder.start_step(run_id, 1, {"prompt": "p", "data": {"n": 1}})
    with initialized_db.connect() as connection:
        row = connection.execute(
            text("SELECT status, input, started_at FROM run_steps WHERE position = 1")
        ).one()
    assert row.status == "running" and row.input == {"prompt": "p", "data": {"n": 1}}
    assert row.started_at is not None
    recorder.finish_step(run_id, 1, StepStatus.SUCCEEDED, output={"ok": True}, duration_ms=12)
    first = recorder.get_steps(run_id)[0]
    assert first.status == StepStatus.SUCCEEDED and first.output == {"ok": True}
    assert first.duration_ms == 12 and first.error is None


def test_failed_step_keeps_error_and_skip_remaining_only_touches_pending(recorder, run_id):
    recorder.create_steps(run_id, KEYS)
    recorder.start_step(run_id, 1, {})
    recorder.finish_step(run_id, 1, StepStatus.SUCCEEDED, output={})
    recorder.start_step(run_id, 2, {})
    recorder.finish_step(run_id, 2, StepStatus.FAILED, error="boom", duration_ms=0)
    recorder.skip_remaining(run_id, 2)
    statuses = [s.status for s in recorder.get_steps(run_id)]
    assert statuses == [StepStatus.SUCCEEDED, StepStatus.FAILED, StepStatus.SKIPPED]
    assert recorder.get_steps(run_id)[1].error == "boom"


def test_update_step_input_replaces_the_input_of_a_running_step(recorder, run_id):
    recorder.create_steps(run_id, KEYS)
    recorder.start_step(run_id, 1, {"v": 1})
    recorder.update_step_input(run_id, 1, {"v": 2})
    assert recorder.get_steps(run_id)[0].input == {"v": 2}


def test_stored_text_is_redacted(recorder, run_id):
    recorder.create_steps(run_id, KEYS)
    recorder.start_step(run_id, 1, {"prompt": "key s3cret-value here", "data": ["s3cret-value", 4]})
    recorder.finish_step(
        run_id, 1, StepStatus.FAILED, output={"raw_response": "s3cret-value"}, error="s3cret-value"
    )
    step = recorder.get_steps(run_id)[0]
    assert "s3cret-value" not in repr(step)
    assert step.input["data"] == ["***", 4]


def test_invalid_transitions_are_refused(recorder, run_id):
    recorder.create_steps(run_id, KEYS)
    with pytest.raises(StateConflictError):
        recorder.finish_step(run_id, 1, StepStatus.SUCCEEDED)
    recorder.start_step(run_id, 1, {})
    with pytest.raises(StateConflictError):
        recorder.start_step(run_id, 1, {})
    with pytest.raises(ValueError):
        recorder.finish_step(run_id, 1, StepStatus.SKIPPED)
    with pytest.raises(NotFoundError):
        recorder.start_step(run_id, 9, {})


def test_unknown_or_finished_run_is_refused(recorder, run_id):
    with pytest.raises(NotFoundError):
        recorder.get_steps(424242)
    recorder.finish_run(run_id, RunStatus.SUCCEEDED)
    with pytest.raises(StateConflictError):
        recorder.create_steps(run_id, KEYS)
