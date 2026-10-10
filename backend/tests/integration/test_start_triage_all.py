import pytest

from bugflow.services import background
from bugflow.services.errors import StateConflictError
from bugflow.services.runs import RunRecorder
from tests_helpers import run_rows, stored_status

pytestmark = pytest.mark.integration


def test_one_run_per_open_bug_in_id_order(runner, initialized_db, three_open_bugs, stand_in):
    stand_in.script_chat([{"role": "Component Classifier", "json": {
        "component": "backend", "justification": "j"}, "delay": 3}])  # fmt: skip
    result = runner.start_run("triage", {"all": True})
    runs = run_rows(initialized_db)
    assert result.run_ids == [r.id for r in runs]
    assert [r.bug_id for r in runs] == three_open_bugs
    assert all(r.type == "triage" and r.status in ("queued", "running") for r in runs)
    assert [stored_status(initialized_db, b) for b in three_open_bugs] == ["processing"] * 3
    assert runner.wait_idle(120)


def test_only_open_bugs_get_a_run(runner, initialized_db, mixed_status_bugs):
    result = runner.start_run("triage", {"all": True})
    assert len(result.run_ids) == 1
    (row,) = run_rows(initialized_db)
    assert row.bug_id == mixed_status_bugs["open"]
    for status in ("processed", "failed", "processing"):
        assert stored_status(initialized_db, mixed_status_bugs[status]) == status
    assert runner.wait_idle(60)


def test_nothing_to_triage(runner, initialized_db, processed_bug, stand_in):
    assert runner.start_run("triage", {"all": True}).run_ids == []
    assert run_rows(initialized_db) == []
    assert runner.wait_idle(5)
    assert stand_in.chat_requests() == []


def test_a_bug_claimed_elsewhere_is_skipped(runner, initialized_db, three_open_bugs, monkeypatch):
    original = background.claim_bug

    def claim(engine, bug_id):
        if bug_id == three_open_bugs[1]:
            raise StateConflictError("claimed elsewhere")
        return original(engine, bug_id)

    monkeypatch.setattr(background, "claim_bug", claim)
    result = runner.start_run("triage", {"all": True})
    assert [r.bug_id for r in run_rows(initialized_db)] == [three_open_bugs[0], three_open_bugs[2]]
    assert len(result.run_ids) == 2
    assert stored_status(initialized_db, three_open_bugs[1]) == "open"
    assert runner.wait_idle(120)


def test_all_or_nothing_preparation(runner, initialized_db, three_open_bugs, monkeypatch):
    original = RunRecorder.create_run
    calls = []

    def create(self, *args, **kwargs):
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("cannot create")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RunRecorder, "create_run", create)
    with pytest.raises(RuntimeError, match="cannot create"):
        runner.start_run("triage", {"all": True})
    assert [stored_status(initialized_db, b) for b in three_open_bugs] == ["failed"] * 3
    runs = run_rows(initialized_db)
    assert [r.status for r in runs] == ["failed", "failed"]
    assert {r.error for r in runs} == {"not started"}
    assert runner.wait_idle(5)
