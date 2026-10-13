"""No response, header, log line or OpenAPI field carries the API key or a connection string."""

from __future__ import annotations

import logging

import pytest

from api_helpers import BASE
from mocks.fake_openai_server import INVALID_KEY
from tests_helpers import wait_final

pytestmark = pytest.mark.integration

GET_PATHS = (
    "/health",
    "/meta/enums",
    "/stats",
    "/bugs",
    "/runs",
    "/search?q=checkout",
    "/nope",
)


def assert_clean(response, secrets: list[str]) -> None:
    haystack = response.text + repr(dict(response.headers))
    for secret in secrets:
        assert secret not in haystack


@pytest.fixture
def secrets(test_engine) -> list[str]:
    return [INVALID_KEY, test_engine.url.render_as_string(hide_password=False)]


def test_failed_health_check_does_not_leak(make_api, secrets):
    client = make_api(env={"OPENAI_API_KEY": INVALID_KEY})
    response = client.get(f"{BASE}/health")
    assert response.status_code == 200
    assert response.json()["llm"] == {"ok": False, "message": "OpenAI authentication failed"}
    assert_clean(response, secrets)


def test_failed_index_run_does_not_leak(make_api, initialized_db, open_bug, secrets):
    client = make_api(env={"OPENAI_API_KEY": INVALID_KEY})
    (run_id,) = client.post(f"{BASE}/admin/index").json()["run_ids"]
    wait_final(initialized_db, run_id)
    response = client.get(f"{BASE}/runs/{run_id}")
    assert response.status_code == 200
    run = response.json()["run"]
    assert (run["status"], run["error"]) == ("failed", "OpenAI authentication failed")
    assert_clean(response, secrets)


def test_openapi_and_docs_contain_no_configured_value(make_api, secrets):
    client = make_api(env={"OPENAI_API_KEY": INVALID_KEY})
    for path in ("/openapi.json", "/docs"):
        response = client.get(path)
        assert response.status_code == 200
        assert_clean(response, secrets)


def test_no_secret_in_any_response(make_api, open_bug, secrets):
    client = make_api(env={"OPENAI_API_KEY": INVALID_KEY})
    for path in GET_PATHS:
        assert_clean(client.get(BASE + path), secrets)
    assert_clean(client.get(f"{BASE}/bugs/{open_bug}/similar"), secrets)
    assert_clean(client.post(f"{BASE}/triage-runs", json={"bug_id": "x"}), secrets)


def test_unexpected_error_is_generic(make_api, open_bug, secrets, caplog):
    leak = f"boom {secrets[0]} {secrets[1]}"

    def fault() -> None:
        raise RuntimeError(leak)

    client = make_api(env={"OPENAI_API_KEY": INVALID_KEY}, fault=fault)
    with caplog.at_level(logging.ERROR):
        response = client.get(f"{BASE}/bugs")
    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "Internal server error",
        "details": [],
    }
    assert_clean(response, secrets)
    assert "Traceback" not in response.text
    assert secrets[0] not in caplog.text
    assert secrets[1] not in caplog.text
    # The fault only affects the bug listing.
    assert client.get(f"{BASE}/stats").status_code == 200
