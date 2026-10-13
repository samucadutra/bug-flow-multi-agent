"""Semantic search endpoint."""

from __future__ import annotations

import pytest

from api_helpers import BASE, index_everything

pytestmark = pytest.mark.integration


@pytest.fixture
def indexed(initialized_db, open_bug, second_open_bug, processed_state, llm_client, stand_in):
    index_everything(initialized_db, llm_client)
    stand_in.reset()


def test_ranked_results(api, indexed):
    response = api.get(f"{BASE}/search", params={"q": "checkout button", "limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 2
    scores = [item["score"] for item in body["items"]]
    assert scores == sorted(scores, reverse=True)
    assert set(body["items"][0]) == {"bug_id", "title", "status", "score"}
    assert body["hint"] == ""


def test_empty_text_makes_no_embedding_call(api, indexed, stand_in):
    response = api.get(f"{BASE}/search", params={"q": "  "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert [d["field"] for d in response.json()["error"]["details"]] == ["q"]
    assert stand_in.embedding_requests() == []


def test_limit_above_the_maximum(api, indexed, stand_in):
    response = api.get(f"{BASE}/search", params={"q": "checkout", "limit": 21})
    assert response.status_code == 422
    assert "limit" in [d["field"] for d in response.json()["error"]["details"]]
    assert stand_in.embedding_requests() == []


def test_long_text_is_reported_on_q(api, indexed):
    response = api.get(f"{BASE}/search", params={"q": "x" * 501})
    assert response.status_code == 422
    assert [d["field"] for d in response.json()["error"]["details"]] == ["q"]


def test_nothing_indexed_returns_the_hint(api, open_bug):
    body = api.get(f"{BASE}/search", params={"q": "checkout"}).json()
    assert body["items"] == []
    assert body["hint"] == "No bugs are indexed; run index"


def test_missing_key_is_unavailable(make_api, indexed):
    client = make_api(env={"OPENAI_API_KEY": None})
    response = client.get(f"{BASE}/search", params={"q": "checkout"})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "OPENAI_API_KEY is not set"
