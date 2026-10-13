"""Request models: the confirm guard, the triage body and malformed JSON (no database needed)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bugflow.api import create_app

URL = "postgresql+psycopg://bugflow:pw@127.0.0.1:1/bugflow"
BASE = "/api/v1"


@pytest.fixture
def client(make_settings):
    return TestClient(create_app(make_settings(DATABASE_URL=URL)), raise_server_exceptions=False)


def fields(response) -> dict[str, str]:
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    return {item["field"]: item["message"] for item in body["details"]}


@pytest.mark.parametrize("path", ["/admin/db/reset", "/bugs/1/reopen"])
def test_confirm_must_be_true(client, path):
    assert fields(client.post(BASE + path, json={"confirm": False})) == {"confirm": "must be true"}
    assert fields(client.post(BASE + path, json={})) == {"confirm": "is required"}
    assert "confirm" in fields(client.post(BASE + path, json={"confirm": "yes"}))
    assert "body" in fields(client.post(BASE + path))
    assert "color" in fields(client.post(BASE + path, json={"confirm": True, "color": "red"}))


def test_triage_body_validation(client):
    url = BASE + "/triage-runs"
    assert "body" in fields(client.post(url))
    assert fields(client.post(url, json={})) == {
        "body": "exactly one of bug_id or all must be given"
    }
    assert set(fields(client.post(url, json={"bug_id": "abc", "color": "red"}))) == {
        "bug_id",
        "color",
    }
    assert "body" in fields(client.post(url, json={"bug_id": 1, "all": True}))
    assert "body" in fields(client.post(url, json={"all": False}))
    assert fields(client.post(url, json={"all": "yes"})) == {"all": "must be a boolean"}
    assert "body" in fields(client.post(url, json=[1]))


def test_malformed_json_is_bad_request(client):
    response = client.post(
        BASE + "/bugs", content="{oops", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_create_bug_validation_is_per_field(client):
    payload = {
        "title": "t" * 121,
        "description": "d",
        "reproduction_steps": "r",
        "system_version": "v",
        "environment": "moon",
        "reporting_team": "qa",
    }
    result = fields(client.post(BASE + "/bugs", json=payload))
    assert result["title"] == "must be at most 120 characters"
    assert result["environment"].startswith("must be one of: production")
    assert "body" in fields(client.post(BASE + "/bugs"))


def test_edit_requires_a_field(client):
    result = fields(client.patch(BASE + "/bugs/1", json={}))
    assert "at least one field is required" in result.values()


def test_query_limits(client):
    assert "limit" in fields(client.get(BASE + "/search", params={"q": "x", "limit": 21}))
    assert "q" in fields(client.get(BASE + "/search"))
    assert "page_size" in fields(client.get(BASE + "/bugs", params={"page_size": 101}))
    assert "type" in fields(client.get(BASE + "/runs", params={"type": "bogus"}))
    assert "limit" in fields(client.get(BASE + "/runs", params={"limit": 0}))
    assert "limit" in fields(client.get(BASE + "/bugs/1/similar", params={"limit": 21}))
    assert "format" in fields(client.get(BASE + "/bugs/1/report", params={"format": "pdf"}))
    assert "id" in fields(client.get(BASE + "/bugs/abc"))


def test_search_empty_text_has_no_embedding_call(client):
    assert "q" in fields(client.get(BASE + "/search", params={"q": "  "}))
