"""Startup recovery through the API lifespan."""

from __future__ import annotations

import pytest

from api_helpers import BASE
from tests_helpers import stored_status

pytestmark = pytest.mark.integration


def test_startup_recovery_marks_interrupted(make_api, initialized_db, interrupted_state):
    client = make_api()
    ids = interrupted_state
    detail = client.get(f"{BASE}/runs/{ids['crashed_run']}").json()
    assert (detail["run"]["status"], detail["run"]["error"]) == ("failed", "interrupted")
    assert [step["status"] for step in detail["steps"]] == [
        "succeeded",
        "failed",
        "skipped",
        "skipped",
        "skipped",
    ]
    assert client.get(f"{BASE}/bugs/{ids['crashed_bug']}").json()["status"] == "failed"
    assert stored_status(initialized_db, ids["finished_bug"]) == "processed"


def test_server_starts_when_the_database_is_down(api_env, caplog):
    from fastapi.testclient import TestClient

    from bugflow.api import create_app
    from bugflow.config import load_settings

    api_env.setenv("DATABASE_URL", "postgresql+psycopg://bugflow:down-pw@127.0.0.1:1/bugflow")
    with TestClient(create_app(load_settings(env_file=None))) as client:
        assert client.get(f"{BASE}/health").status_code == 200
        assert client.get(f"{BASE}/stats").status_code == 503
    assert "down-pw" not in caplog.text
