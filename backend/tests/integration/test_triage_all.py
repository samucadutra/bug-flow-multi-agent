import pytest
from sqlalchemy import text

from bugflow.services import triage as triage_module
from bugflow.services.errors import StateConflictError
from bugflow.services.triage import triage_all
from mocks.fake_openai_server import default_reply
from tests_helpers import stored_status

pytestmark = pytest.mark.integration


def statuses(engine):
    with engine.connect() as connection:
        return dict(connection.execute(text("SELECT title, status FROM bugs")).all())


def test_a_failure_does_not_stop_the_batch(initialized_db, three_open_bugs, get_client, stand_in):
    wrong = default_reply("Severity Classifier")
    wrong["severity"] = "high"
    stand_in.script_chat(
        [{"role": "Severity Classifier", "contains": "Bug two", "json": wrong, "repeat": 2}]
    )
    outcomes = triage_all(initialized_db, get_client)
    assert [o.bug_id for o in outcomes] == three_open_bugs
    assert [o.status.value for o in outcomes] == ["processed", "failed", "processed"]
    assert statuses(initialized_db) == {
        "Bug one": "processed",
        "Bug two": "failed",
        "Bug three": "processed",
    }
    with initialized_db.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM runs WHERE type = 'triage'")).scalar()
            == 3
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM bugs WHERE status = 'processing'")
            ).scalar()
            == 0
        )


def test_only_open_bugs_are_processed(initialized_db, mixed_status_bugs, get_client):
    ids = mixed_status_bugs
    outcomes = triage_all(initialized_db, get_client)
    assert [o.bug_id for o in outcomes] == [ids["open"]] and outcomes[0].processed
    assert stored_status(initialized_db, ids["processed"]) == "processed"
    assert stored_status(initialized_db, ids["failed"]) == "failed"
    assert stored_status(initialized_db, ids["processing"]) == "processing"


def test_nothing_to_triage(initialized_db, processed_bug, get_client, stand_in):
    assert triage_all(initialized_db, get_client) == []
    with initialized_db.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM runs")).scalar() == 0
    assert stand_in.chat_requests() == []


def test_bugs_are_processed_one_at_a_time_in_id_order(initialized_db, three_open_bugs, get_client):
    triage_all(initialized_db, get_client)
    with initialized_db.connect() as connection:
        runs = connection.execute(
            text("SELECT bug_id, started_at, finished_at FROM runs ORDER BY id")
        ).all()
    assert [run.bug_id for run in runs] == three_open_bugs
    for current, following in zip(runs, runs[1:], strict=False):
        assert current.finished_at <= following.started_at


def test_callbacks_report_steps_and_outcomes(initialized_db, three_open_bugs, get_client):
    steps, outcomes = [], []
    triage_all(initialized_db, get_client, on_step=steps.append, on_outcome=outcomes.append)
    assert len(steps) == 15 and [o.bug_id for o in outcomes] == three_open_bugs


def test_a_claim_lost_to_another_process_is_skipped(
    initialized_db, three_open_bugs, get_client, monkeypatch
):
    real = triage_module.triage_bug

    def flaky(engine, get_client, bug_id, *args, **kwargs):
        if bug_id == three_open_bugs[1]:
            raise StateConflictError(f"Bug {bug_id} is already being processed")
        return real(engine, get_client, bug_id, *args, **kwargs)

    monkeypatch.setattr(triage_module, "triage_bug", flaky)
    outcomes = triage_all(initialized_db, get_client)
    assert [o.bug_id for o in outcomes] == [three_open_bugs[0], three_open_bugs[2]]
