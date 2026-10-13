"""Health, enums and stats."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine

from api_helpers import BASE
from bugflow.db.engine import session_factory
from bugflow.db.models import Bug
from bugflow.enums import ENUM_CLASSES, Component, Severity, all_enums, codes
from tests_helpers import add_bug

pytestmark = pytest.mark.integration


def test_all_checks_pass(api):
    body = api.get(f"{BASE}/health").json()
    assert body["ok"] is True
    for name in ("database", "vector_search", "llm"):
        assert body[name]["ok"] is True


def test_missing_key_fails_only_the_llm_check(make_api):
    body = make_api(env={"OPENAI_API_KEY": None}).get(f"{BASE}/health").json()
    assert body["llm"] == {"ok": False, "message": "OPENAI_API_KEY is not set"}
    assert body["database"]["ok"] and body["vector_search"]["ok"]
    assert body["ok"] is False


def test_rejected_key_message_is_fixed(make_api):
    client = make_api(env={"OPENAI_API_KEY": "sk-test-invalid"})
    response = client.get(f"{BASE}/health")
    assert response.status_code == 200
    assert response.json()["llm"]["message"] == "OpenAI authentication failed"
    assert "sk-test-invalid" not in response.text


def test_unreachable_database_is_reported_as_data(api_env):
    from fastapi.testclient import TestClient

    from bugflow.api import create_app
    from bugflow.config import load_settings

    api_env.setenv("DATABASE_URL", "postgresql+psycopg://bugflow:unreach-pw@127.0.0.1:1/bugflow")
    with TestClient(create_app(load_settings(env_file=None))) as dead:
        response = dead.get(f"{BASE}/health")
        assert response.status_code == 200
        assert response.json()["database"] == {
            "ok": False,
            "message": "Cannot connect to the database",
        }
        assert "unreach-pw" not in response.text
        listing = dead.get(f"{BASE}/bugs")
        assert listing.status_code == 503
        assert listing.json()["error"]["message"] == "Cannot connect to the database"
        assert "unreach-pw" not in listing.text


def test_enums_endpoint_matches_module(api):
    body = api.get(f"{BASE}/meta/enums").json()["enums"]
    expected = all_enums()
    assert [item["name"] for item in body] == [item.name for item in expected]
    assert len(body) == 11
    for served, descriptor in zip(body, expected, strict=True):
        assert [v["code"] for v in served["values"]] == [v.code for v in descriptor.values]
        assert [v["label"] for v in served["values"]] == [v.label for v in descriptor.values]
        assert all(v["label"] for v in served["values"])
    by_name = {item["name"]: item for item in body}
    assert [v["code"] for v in by_name["BugStatus"]["values"]] == [
        "open",
        "processing",
        "processed",
        "failed",
    ]
    for name in ("Component", "Severity"):
        assert all(v["definition"] for v in by_name[name]["values"])
    assert len(ENUM_CLASSES) == 11


def test_stats_on_an_empty_database(api):
    body = api.get(f"{BASE}/stats").json()
    assert body["total"] == 0
    assert set(body["by_status"]) == {"open", "processing", "processed", "failed"}
    assert body["by_component"] == dict.fromkeys(codes(Component), 0)
    assert body["by_severity"] == dict.fromkeys(codes(Severity), 0)


def test_stats_counts(api, initialized_db: Engine, processed_state):
    add_bug(initialized_db)
    add_bug(initialized_db, status="processing", title="Busy checkout bug")
    body = api.get(f"{BASE}/stats").json()
    assert body["total"] == 3
    assert body["by_status"] == {"open": 1, "processing": 1, "processed": 1, "failed": 0}
    assert body["by_component"]["frontend"] == 1
    assert sum(body["by_component"].values()) == 1
    assert body["by_severity"] == {"critical": 0, "major": 1, "minor": 0}
    with session_factory(initialized_db)() as session:
        assert session.query(Bug).count() == 3
