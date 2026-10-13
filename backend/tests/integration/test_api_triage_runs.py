"""`POST /triage-runs` and the run listing and detail endpoints."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import text

from api_helpers import BASE, add_seed_run
from tests_helpers import add_bug, run_rows, stored_status, wait_final, wait_until

pytestmark = pytest.mark.integration

MISSING = 999999


def test_single_triage_returns_202_fast_and_completes(api, initialized_db, open_bug):
    started = time.monotonic()
    response = api.post(f"{BASE}/triage-runs", json={"bug_id": open_bug})
    assert time.monotonic() - started < 1
    assert response.status_code == 202
    (run_id,) = response.json()["run_ids"]
    run = api.get(f"{BASE}/runs/{run_id}").json()["run"]
    assert (run["bug_id"], run["type"]) == (open_bug, "triage")
    wait_final(initialized_db, run_id)
    detail = api.get(f"{BASE}/runs/{run_id}").json()
    assert detail["run"]["status"] == "succeeded"
    assert [step["status"] for step in detail["steps"]] == ["succeeded"] * 5
    assert stored_status(initialized_db, open_bug) == "processed"
    assert api.get(f"{BASE}/bugs/{open_bug}/report", params={"format": "md"}).status_code == 200
    with initialized_db.connect() as connection:
        for table in (
            "component_classifications",
            "severity_classifications",
            "technical_analyses",
            "resolution_plans",
            "bug_reports",
        ):
            query = text(f"SELECT count(*) FROM {table} WHERE bug_id = :id")  # noqa: S608
            assert connection.execute(query, {"id": open_bug}).scalar_one() == 1


def test_triage_all_returns_a_run_per_open_bug_and_runs_them_one_at_a_time(
    api, initialized_db, open_bug, second_open_bug
):
    response = api.post(f"{BASE}/triage-runs", json={"all": True})
    assert response.status_code == 202
    run_ids = response.json()["run_ids"]
    assert len(run_ids) == 2 and len(set(run_ids)) == 2
    for run_id in run_ids:
        wait_final(initialized_db, run_id)
    first, second = sorted(run_rows(initialized_db), key=lambda row: row.id)
    assert (first.status, second.status) == ("succeeded", "succeeded")
    with initialized_db.connect() as connection:
        second_work_began = connection.execute(
            text("SELECT min(started_at) FROM run_steps WHERE run_id = :id"), {"id": second.id}
        ).scalar_one()
    assert first.finished_at <= second_work_began
    assert stored_status(initialized_db, open_bug) == "processed"
    assert stored_status(initialized_db, second_open_bug) == "processed"


def test_triage_all_without_open_bugs(api):
    response = api.post(f"{BASE}/triage-runs", json={"all": True})
    assert response.status_code == 202
    assert response.json() == {"run_ids": []}


def test_processing_bug_is_a_conflict(api, initialized_db):
    bug_id = add_bug(initialized_db, status="processing", title="Busy checkout bug")
    response = api.post(f"{BASE}/triage-runs", json={"bug_id": bug_id})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "state_conflict"
    assert run_rows(initialized_db) == []


def test_unknown_bug(api):
    response = api.post(f"{BASE}/triage-runs", json={"bug_id": MISSING})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.parametrize(
    ("kwargs", "fields"),
    [
        ({}, {"body"}),
        ({"json": {}}, {"body"}),
        ({"json": {"bug_id": "abc", "color": "red"}}, {"bug_id", "color"}),
        ({"json": {"bug_id": 1, "all": True}}, {"body"}),
    ],
)
def test_invalid_bodies_create_no_run(api, initialized_db, open_bug, kwargs, fields):
    response = api.post(f"{BASE}/triage-runs", **kwargs)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert {d["field"] for d in response.json()["error"]["details"]} == fields
    assert run_rows(initialized_db) == []


def test_run_listing_is_newest_first_and_filterable(api, initialized_db, processed_state):
    seed_id = add_seed_run(initialized_db)
    items = api.get(f"{BASE}/runs").json()["items"]
    assert [item["id"] for item in items] == [processed_state["run_id"], seed_id]
    filtered = api.get(f"{BASE}/runs", params={"type": "seed", "status": "succeeded"}).json()
    assert [item["id"] for item in filtered["items"]] == [seed_id]
    assert len(api.get(f"{BASE}/runs", params={"limit": 1}).json()["items"]) == 1


def test_run_listing_rejects_an_unknown_type(api, initialized_db):
    add_seed_run(initialized_db)
    response = api.get(f"{BASE}/runs", params={"type": "bogus"})
    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert [d["field"] for d in details] == ["type"]
    assert "triage" in details[0]["message"]


def test_run_detail(api, processed_state):
    detail = api.get(f"{BASE}/runs/{processed_state['run_id']}").json()
    assert detail["run"]["status"] == "succeeded"
    assert (detail["run"]["progress_done"], detail["run"]["progress_total"]) == (5, 5)
    assert [step["position"] for step in detail["steps"]] == [1, 2, 3, 4, 5]
    for step in detail["steps"]:
        assert step["agent_key"] and step["status"] == "succeeded"
        assert step["input"] is not None and step["output"] is not None
        assert step["duration_ms"] is not None
    assert [log["message"] for log in detail["logs"]] == [f"log line {n}" for n in range(1, 5)]


def test_unknown_run(api):
    response = api.get(f"{BASE}/runs/{MISSING}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_reopen_and_triage_again_keeps_the_first_run(api, initialized_db, open_bug):
    first = api.post(f"{BASE}/triage-runs", json={"bug_id": open_bug}).json()["run_ids"][0]
    wait_final(initialized_db, first)
    wait_until(lambda: stored_status(initialized_db, open_bug) == "processed")
    assert api.post(f"{BASE}/bugs/{open_bug}/reopen", json={"confirm": True}).status_code == 200
    second = api.post(f"{BASE}/triage-runs", json={"bug_id": open_bug}).json()["run_ids"][0]
    wait_final(initialized_db, second)
    runs = api.get(f"{BASE}/bugs/{open_bug}/runs").json()["items"]
    assert [run["id"] for run in runs] == [second, first]
    assert [run["status"] for run in runs] == ["succeeded", "succeeded"]
    assert len(api.get(f"{BASE}/runs/{first}").json()["steps"]) == 5
    report = api.get(f"{BASE}/bugs/{open_bug}/report", params={"format": "md"})
    assert report.text.startswith("# Checkout button does nothing on Safari 17")
