import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from bugflow.db.engine import session_factory
from bugflow.enums import BugStatus, RunStatus, StepStatus
from bugflow.services import triage as triage_module
from bugflow.services.runs import RunRecorder
from bugflow.services.triage import register_result_hook, triage_bug, unregister_result_hook
from tests_helpers import RESULT_TABLES, add_bug, result_row_counts, stored_status

pytestmark = pytest.mark.integration


def recorder_for(engine):
    return RunRecorder(session_factory(engine))


def test_a_failing_hook_leaves_no_results(initialized_db, open_bug, get_client, failing_hook):
    register_result_hook(failing_hook)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.status == BugStatus.FAILED
    assert outcome.error == "Result hook failed: forced failure"
    assert stored_status(initialized_db, open_bug) == "failed"
    assert result_row_counts(initialized_db, open_bug) == dict.fromkeys(RESULT_TABLES, 0)
    recorder = recorder_for(initialized_db)
    assert [s.status for s in recorder.get_steps(outcome.run_id)] == [StepStatus.SUCCEEDED] * 5
    run = recorder.get_run(outcome.run_id)
    assert run.status == RunStatus.FAILED and run.error == outcome.error


def test_hooks_run_inside_the_result_transaction(
    initialized_db, open_bug, get_client, recording_hook
):
    register_result_hook(recording_hook)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.processed
    assert recording_hook.calls == [dict.fromkeys(RESULT_TABLES, 1)]
    assert recording_hook.statuses == ["processing"]
    assert stored_status(initialized_db, open_bug) == "processed"


def test_hook_writes_are_invisible_to_other_connections_until_the_commit(
    initialized_db, open_bug, get_client
):
    seen = []

    def probe(session, bug_id, results):
        with initialized_db.connect() as other:
            seen.append(other.execute(text("SELECT count(*) FROM bug_reports")).scalar_one())

    register_result_hook(probe)
    assert triage_bug(initialized_db, get_client, open_bug).processed
    assert seen == [0]


def test_hooks_run_in_registration_order_and_can_be_unregistered(
    initialized_db, open_bug, get_client
):
    calls = []

    def first(session, bug_id, results):
        calls.append("first")

    def second(session, bug_id, results):
        calls.append("second")

    register_result_hook(first)
    register_result_hook(second)
    assert triage_bug(initialized_db, get_client, open_bug).processed
    assert calls == ["first", "second"]
    unregister_result_hook(first)
    unregister_result_hook(first)  # unknown hooks are ignored
    calls.clear()
    other = add_bug(initialized_db, title="Another bug")
    assert triage_bug(initialized_db, get_client, other).processed
    assert calls == ["second"]


def test_a_hook_that_writes_is_rolled_back_with_the_results(initialized_db, open_bug, get_client):
    def writes(session, bug_id, results):
        session.execute(
            text("UPDATE bug_reports SET markdown = 'x' WHERE bug_id = :id"), {"id": bug_id}
        )
        raise RuntimeError("late failure")

    register_result_hook(writes)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.error == "Result hook failed: late failure"
    assert result_row_counts(initialized_db, open_bug) == dict.fromkeys(RESULT_TABLES, 0)


def test_a_hook_that_changes_the_status_makes_the_write_fail(initialized_db, open_bug, get_client):
    def changes_status(session, bug_id, results):
        session.execute(text("UPDATE bugs SET status = 'open' WHERE id = :id"), {"id": bug_id})

    register_result_hook(changes_status)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.error == f"Bug {open_bug} is no longer being processed"
    assert stored_status(initialized_db, open_bug) == "failed"
    assert result_row_counts(initialized_db, open_bug) == dict.fromkeys(RESULT_TABLES, 0)


def test_a_database_error_in_the_final_write_fails_the_bug(
    initialized_db, open_bug, get_client, monkeypatch
):
    def broken(*args, **kwargs):
        raise IntegrityError("INSERT ...", {}, Exception("duplicate key value\nDETAIL: more"))

    monkeypatch.setattr(triage_module, "_write_results", broken)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert outcome.status == BugStatus.FAILED
    assert outcome.error == "Result write failed: duplicate key value"
    assert stored_status(initialized_db, open_bug) == "failed"
    run = recorder_for(initialized_db).get_run(outcome.run_id)
    assert run.status == RunStatus.FAILED and run.error == outcome.error


def test_hook_error_text_is_redacted(initialized_db, open_bug, get_client):
    def leaking(session, bug_id, results):
        raise RuntimeError("token sk-abcdefghijklmnopqrstuvwxyz0123")

    register_result_hook(leaking)
    outcome = triage_bug(initialized_db, get_client, open_bug)
    assert "sk-abcdefghijklmnopqrstuvwxyz0123" not in repr(outcome)
    assert outcome.error == "Result hook failed: token ***"
