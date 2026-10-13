"""The API smoke path (health, create bug, list bugs) without a real LLM."""

from __future__ import annotations

import pytest

from api_helpers import BASE, create_body

pytestmark = pytest.mark.integration


def test_health_create_and_list(api):
    health = api.get(f"{BASE}/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    created = api.post(f"{BASE}/bugs", json=create_body(title="Login page shows blank screen"))
    assert created.status_code == 201
    assert created.json()["status"] == "open"

    listing = api.get(f"{BASE}/bugs")
    assert listing.status_code == 200
    body = listing.json()
    assert (body["total"], body["page"], body["page_size"]) == (1, 1, 20)
    assert body["items"][0]["title"] == "Login page shows blank screen"


def test_smoke_without_a_key(make_api):
    client = make_api(env={"OPENAI_API_KEY": None})
    health = client.get(f"{BASE}/health").json()
    assert health["ok"] is False
    assert health["llm"] == {"ok": False, "message": "OPENAI_API_KEY is not set"}
    assert client.post(f"{BASE}/bugs", json=create_body()).status_code == 201
    assert client.get(f"{BASE}/bugs").json()["total"] == 1
