"""Administrative endpoints: init, seed, reset and index."""

from __future__ import annotations

import time

import pytest
from sqlalchemy import text

from api_helpers import BASE
from bugflow.db.engine import session_factory
from bugflow.db.models import Bug, BugEmbedding, Run
from tests_helpers import add_bug, wait_final

pytestmark = pytest.mark.integration


def run_status(api, run_id: int) -> dict:
    return api.get(f"{BASE}/runs/{run_id}").json()


def counts(engine) -> dict[str, int]:
    with session_factory(engine)() as session:
        return {
            "bugs": session.query(Bug).count(),
            "runs": session.query(Run).count(),
            "embeddings": session.query(BugEmbedding).count(),
        }


# --- init ---


def test_init_creates_the_schema(make_api_fresh, fresh_schema):
    client = make_api_fresh()
    response = client.post(f"{BASE}/admin/db/init")
    assert response.status_code == 200
    body = response.json()
    assert body["applied_revisions"]
    assert body["messages"] == [f"Applied migration {r}" for r in body["applied_revisions"]]
    with fresh_schema.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM bugs")).scalar_one() == 0
        assert (
            connection.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            ).scalar_one()
            == 1
        )
    # The pooled connections still work after the schema was created.
    assert client.get(f"{BASE}/bugs").json()["total"] == 0


def test_init_is_idempotent(api):
    response = api.post(f"{BASE}/admin/db/init")
    assert response.status_code == 200
    assert response.json()["applied_revisions"] == []
    assert response.json()["messages"] == ["Database schema is already up to date"]


# --- seed ---


def test_seed_is_accepted_at_once_and_completes(api, initialized_db):
    started = time.monotonic()
    response = api.post(f"{BASE}/admin/db/seed")
    assert time.monotonic() - started < 1
    assert response.status_code == 202
    (run_id,) = response.json()["run_ids"]
    assert api.get(f"{BASE}/runs/{run_id}").json()["run"]["type"] == "seed"
    wait_final(initialized_db, run_id)
    detail = run_status(api, run_id)
    assert detail["run"]["status"] == "succeeded"
    assert (detail["run"]["progress_done"], detail["run"]["progress_total"]) == (20, 20)
    assert detail["logs"]
    listing = api.get(f"{BASE}/bugs", params={"page_size": 100}).json()
    assert listing["total"] == 20
    assert {item["status"] for item in listing["items"]} == {"open"}


def test_seed_on_an_uninitialized_database(make_api_fresh):
    response = make_api_fresh().post(f"{BASE}/admin/db/seed")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "state_conflict"
    assert "init" in response.json()["error"]["message"]


# --- index ---


def test_index_is_accepted_at_once_and_completes(api, initialized_db, llm_client):
    for number in range(20):
        add_bug(initialized_db, title=f"Bug number {number}")
    started = time.monotonic()
    response = api.post(f"{BASE}/admin/index")
    assert time.monotonic() - started < 1
    assert response.status_code == 202
    (run_id,) = response.json()["run_ids"]
    wait_final(initialized_db, run_id)
    detail = run_status(api, run_id)
    assert detail["run"]["type"] == "index"
    assert detail["run"]["status"] == "succeeded"
    assert (detail["run"]["progress_done"], detail["run"]["progress_total"]) == (20, 20)
    assert detail["logs"]
    assert counts(initialized_db)["embeddings"] == 20


def test_index_with_a_missing_key_fails_the_run(make_api, initialized_db, open_bug):
    client = make_api(env={"OPENAI_API_KEY": None})
    response = client.post(f"{BASE}/admin/index")
    assert response.status_code == 202
    (run_id,) = response.json()["run_ids"]
    wait_final(initialized_db, run_id)
    run = client.get(f"{BASE}/runs/{run_id}").json()["run"]
    assert (run["status"], run["error"]) == ("failed", "OPENAI_API_KEY is not set")
    assert counts(initialized_db)["embeddings"] == 0


# --- reset ---


def test_confirmed_reset(api, initialized_db, processed_state, open_bug):
    response = api.post(f"{BASE}/admin/db/reset", json={"confirm": True})
    assert response.status_code == 200
    assert response.json()["applied_revisions"]
    after = counts(initialized_db)
    assert after["bugs"] == 0 and after["embeddings"] == 0
    assert after["runs"] == 1  # only the recorded reset run
    assert api.get(f"{BASE}/stats").json()["total"] == 0
    assert api.post(f"{BASE}/bugs", json={}).status_code == 422


@pytest.mark.parametrize("body", [{"confirm": False}, None])
def test_reset_without_confirmation_deletes_nothing(api, initialized_db, processed_state, body):
    before = counts(initialized_db)
    response = api.post(f"{BASE}/admin/db/reset", **({"json": body} if body else {}))
    assert response.status_code == 422
    fields = [d["field"] for d in response.json()["error"]["details"]]
    assert fields == (["confirm"] if body else ["body"])
    assert counts(initialized_db) == before
