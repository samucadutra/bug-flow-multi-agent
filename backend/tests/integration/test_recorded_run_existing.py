import pytest

from bugflow.db.engine import session_factory
from bugflow.enums import RunType
from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.operations import run_index, run_seed
from bugflow.services.runs import RunRecorder, recorded_run
from tests_helpers import log_rows, run_row, run_rows

pytestmark = pytest.mark.integration


def recorder_of(engine):
    return RunRecorder(session_factory(engine))


def test_recorded_run_uses_the_existing_queued_run(initialized_db):
    recorder = recorder_of(initialized_db)
    run_id = recorder.create_run(RunType.SEED)
    with recorded_run(recorder, RunType.SEED, run_id=run_id) as run:
        assert run.run_id == run_id
        assert run_row(initialized_db, run_id).status == "running"
    assert len(run_rows(initialized_db)) == 1
    assert run_row(initialized_db, run_id).status == "succeeded"


def test_a_failure_marks_the_given_run_failed(initialized_db):
    recorder = recorder_of(initialized_db)
    run_id = recorder.create_run(RunType.SEED)
    with pytest.raises(RuntimeError), recorded_run(recorder, RunType.SEED, run_id=run_id):
        raise RuntimeError("bad")
    row = run_row(initialized_db, run_id)
    assert (row.status, row.error) == ("failed", "bad")


def test_a_finished_or_unknown_run_id_raises(initialized_db):
    recorder = recorder_of(initialized_db)
    run_id = recorder.create_run(RunType.SEED)
    recorder.start_run(run_id)
    with pytest.raises(StateConflictError), recorded_run(recorder, RunType.SEED, run_id=run_id):
        pass
    with pytest.raises(NotFoundError), recorded_run(recorder, RunType.SEED, run_id=99999):
        pass


def test_run_seed_with_a_run_id(initialized_db):
    recorder = recorder_of(initialized_db)
    run_id = recorder.create_run(RunType.SEED)
    run_seed(initialized_db, run_id=run_id)
    (row,) = run_rows(initialized_db)
    assert (row.id, row.type, row.status) == (run_id, "seed", "succeeded")
    assert (row.progress_done, row.progress_total) == (20, 20)
    assert [line.message for line in log_rows(initialized_db, run_id)] == ["Seeded 20 bugs"]


def test_run_index_with_a_run_id(seeded_db, get_client):
    recorder = recorder_of(seeded_db)
    run_id = recorder.create_run(RunType.INDEX)
    run_index(seeded_db, get_client, run_id=run_id)
    (row,) = run_rows(seeded_db)
    assert (row.id, row.status, row.progress_done, row.progress_total) == (
        run_id,
        "succeeded",
        20,
        20,
    )


def test_a_failing_index_marks_the_given_run_failed(seeded_db, no_key_factory):
    recorder = recorder_of(seeded_db)
    run_id = recorder.create_run(RunType.INDEX)
    with pytest.raises(Exception, match="OPENAI_API_KEY is not set"):
        run_index(seeded_db, no_key_factory, run_id=run_id)
    row = run_row(seeded_db, run_id)
    assert (row.status, row.error) == ("failed", "OPENAI_API_KEY is not set")


def test_calls_without_a_run_id_create_their_own_run(initialized_db):
    run_seed(initialized_db)
    (row,) = run_rows(initialized_db)
    assert row.type == "seed" and row.status == "succeeded"
