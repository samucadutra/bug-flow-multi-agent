"""The run event stream: finished run, resume, live run, errors."""

from __future__ import annotations

import threading

import pytest

from api_helpers import BASE, parse_sse
from mocks.fake_openai_server import default_reply
from tests_helpers import wait_until

pytestmark = pytest.mark.integration

MISSING = 999999
ROLES = (
    "Component Classifier",
    "Severity Classifier",
    "Technical Analyst",
    "Resolution Manager",
    "Bug Documenter",
)


def stream(client, url: str, **kwargs):
    with client.stream("GET", url, **kwargs) as response:
        text = "".join(response.iter_text())
        return response, parse_sse(text)


def test_stream_of_a_finished_run_closes_on_the_terminal_event(api, processed_state):
    response, frames = stream(api, f"{BASE}/runs/{processed_state['run_id']}/events")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    kinds = [frame["event"] for frame in frames]
    assert kinds.count("step") == 5 and kinds.count("log") == 4
    assert kinds[-1] == "run"
    assert frames[-1]["data"]["run"]["status"] == "succeeded"
    for frame in frames:
        assert frame["id"] == frame["data"]["cursor"]
        assert frame["data"]["type"] == frame["event"]


def test_events_match_polling(api, processed_state):
    run_id = processed_state["run_id"]
    _, frames = stream(api, f"{BASE}/runs/{run_id}/events")
    detail = api.get(f"{BASE}/runs/{run_id}").json()
    assert [f["data"]["step"] for f in frames if f["event"] == "step"] == detail["steps"]
    assert [f["data"]["log"] for f in frames if f["event"] == "log"] == detail["logs"]
    assert frames[-1]["data"]["run"] == detail["run"]


def test_resume_from_a_cursor_with_the_header(api, processed_state):
    url = f"{BASE}/runs/{processed_state['run_id']}/events"
    _, frames = stream(api, url)
    first = frames[0]
    response, resumed = stream(api, url, headers={"Last-Event-ID": first["id"]})
    assert response.status_code == 200
    assert first["id"] not in [frame["id"] for frame in resumed]
    assert len(resumed) == len(frames) - 1
    assert resumed[-1]["event"] == "run"


def test_resume_from_a_cursor_with_the_query(api, processed_state):
    url = f"{BASE}/runs/{processed_state['run_id']}/events"
    _, frames = stream(api, url)
    _, resumed = stream(api, url, params={"after": frames[-2]["id"]})
    assert [frame["event"] for frame in resumed] == ["run"]


def test_unknown_run_is_a_json_404(api):
    response = api.get(f"{BASE}/runs/{MISSING}/events")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/json"
    assert response.json()["error"]["code"] == "not_found"


def test_invalid_cursor(api, processed_state):
    response = api.get(
        f"{BASE}/runs/{processed_state['run_id']}/events", params={"after": "garbage"}
    )
    assert response.status_code == 422
    assert [d["field"] for d in response.json()["error"]["details"]] == ["after"]


def test_live_stream_of_a_slow_triage(api, initialized_db, open_bug, stand_in):
    stand_in.script_chat(
        [{"role": role, "delay": 0.5, "json": default_reply(role)} for role in ROLES]
    )
    run_id = api.post(f"{BASE}/triage-runs", json={"bug_id": open_bug}).json()["run_ids"][0]
    assert api.get(f"{BASE}/runs/{run_id}").json()["run"]["status"] in ("queued", "running")
    result: dict = {}

    def read() -> None:
        result["response"], result["frames"] = stream(api, f"{BASE}/runs/{run_id}/events")

    reader = threading.Thread(target=read)
    reader.start()
    reader.join(timeout=60)
    assert not reader.is_alive()
    frames = result["frames"]
    succeeded = [
        f["data"]["step"]["position"]
        for f in frames
        if f["event"] == "step" and f["data"]["step"]["status"] == "succeeded"
    ]
    assert succeeded == [1, 2, 3, 4, 5]
    assert any(f["event"] == "log" for f in frames)
    assert frames[-1]["event"] == "run"
    assert frames[-1]["data"]["run"]["status"] == "succeeded"
    wait_until(lambda: api.get(f"{BASE}/bugs/{open_bug}").json()["status"] == "processed")
