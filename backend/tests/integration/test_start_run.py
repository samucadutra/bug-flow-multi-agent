import threading
import time

import pytest
from sqlalchemy import text

from bugflow.services.background import BackgroundRunner
from bugflow.services.errors import (
    NotFoundError,
    SchemaNotInitializedError,
    StateConflictError,
    ValidationFailedError,
)
from mocks.fake_openai_server import default_reply
from tests_helpers import run_row, run_rows, stored_status, wait_final

pytestmark = pytest.mark.integration


def test_triage_start_returns_immediately_with_a_queued_or_running_run(
    runner, initialized_db, open_bug, stand_in
):
    stand_in.script_chat([{"role": "Component Classifier", "json": default_reply(
        "Component Classifier"), "delay": 3}])  # fmt: skip
    started = time.monotonic()
    result = runner.start_run("triage", {"bug_id": open_bug})
    assert time.monotonic() - started < 1
    row = run_row(initialized_db, result.run_id)
    assert (row.type, row.bug_id) == ("triage", open_bug)
    assert row.status in ("queued", "running")
    assert stored_status(initialized_db, open_bug) == "processing"
    assert runner.wait_idle(60)


def test_processing_bug_is_refused(runner, initialized_db, processing_bug):
    with pytest.raises(StateConflictError) as caught:
        runner.start_run("triage", {"bug_id": processing_bug})
    assert caught.value.message == f"Bug {processing_bug} is already being processed"
    assert stored_status(initialized_db, processing_bug) == "processing"
    assert run_rows(initialized_db) == []


def test_processed_bug_is_refused(runner, initialized_db, processed_bug):
    with pytest.raises(StateConflictError) as caught:
        runner.start_run("triage", {"bug_id": processed_bug})
    assert (
        caught.value.message == f"Bug {processed_bug} has already been processed; reopen it first"
    )
    assert run_rows(initialized_db) == []


def test_unknown_bug(runner, initialized_db):
    with pytest.raises(NotFoundError, match="^Bug 999999 not found$"):
        runner.start_run("triage", {"bug_id": 999999})
    assert run_rows(initialized_db) == []


def test_failed_bug_can_be_started_again(runner, initialized_db, failed_bug):
    result = runner.start_run("triage", {"bug_id": failed_bug})
    assert run_row(initialized_db, result.run_id).bug_id == failed_bug
    assert stored_status(initialized_db, failed_bug) in ("processing", "processed")
    assert runner.wait_idle(60)


def test_concurrent_starts_have_one_winner(runner, initialized_db, open_bug):
    barrier = threading.Barrier(2)
    outcomes = []

    def call():
        barrier.wait()
        try:
            outcomes.append(runner.start_run("triage", {"bug_id": open_bug}))
        except StateConflictError as exc:
            outcomes.append(exc)

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(type(o).__name__ for o in outcomes) == ["StartResult", "StateConflictError"]
    assert len(run_rows(initialized_db, "type = 'triage'")) == 1
    assert runner.wait_idle(60)


def test_validation_errors_create_nothing(runner, initialized_db, open_bug):
    with pytest.raises(ValidationFailedError) as caught:
        runner.start_run("triage", {})
    assert [(e.field, e.message) for e in caught.value.field_errors] == [
        ("params", "Specify exactly one of bug_id or all")
    ]
    with pytest.raises(ValidationFailedError) as caught:
        runner.start_run("reset", {})
    assert caught.value.field_errors[0].field == "kind"
    assert run_rows(initialized_db) == []
    assert stored_status(initialized_db, open_bug) == "open"


def test_index_start_creates_a_run_before_returning(runner, seeded_db):
    started = time.monotonic()
    result = runner.start_run("index", {})
    assert time.monotonic() - started < 1
    row = run_row(seeded_db, result.run_id)
    assert row.type == "index" and row.bug_id is None
    assert wait_final(seeded_db, result.run_id).status == "succeeded"


def test_seed_needs_an_initialized_schema(fresh_schema, get_client):
    runner = BackgroundRunner(fresh_schema, get_client)
    with pytest.raises(SchemaNotInitializedError):
        runner.start_run("seed", {})
    with fresh_schema.connect() as connection:
        tables = connection.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        ).scalar()
    assert tables == 0


def test_a_run_creation_failure_returns_the_bug_to_failed(
    runner, initialized_db, open_bug, monkeypatch
):
    from bugflow.services.runs import RunRecorder

    def broken(self, *args, **kwargs):
        raise RuntimeError("no run")

    monkeypatch.setattr(RunRecorder, "create_run", broken)
    with pytest.raises(RuntimeError):
        runner.start_run("triage", {"bug_id": open_bug})
    assert stored_status(initialized_db, open_bug) == "failed"


def test_start_after_shutdown_is_refused(runner, open_bug):
    runner.shutdown(5)
    with pytest.raises(RuntimeError):
        runner.start_run("triage", {"bug_id": open_bug})
