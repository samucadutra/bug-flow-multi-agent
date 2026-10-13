"""SSE framing and cursor selection."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from bugflow.api.sse import format_event, frames, resolve_cursor
from bugflow.enums import RunStatus, StepStatus
from bugflow.services.run_events import LogEvent, RunStatusEvent, StepEvent
from bugflow.services.schemas import RunLogRead, RunRead, RunStepRead

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def step_event() -> StepEvent:
    step = RunStepRead(
        id=1,
        run_id=5,
        position=1,
        agent_key="component_classifier",
        status=StepStatus.SUCCEEDED,
        input=None,
        output=None,
        error=None,
        started_at=None,
        duration_ms=3,
    )
    return StepEvent(cursor="0.s.-", step=step)


def run_event() -> RunStatusEvent:
    run = RunRead(
        id=5,
        type="triage",
        bug_id=1,
        status=RunStatus.SUCCEEDED,
        progress_done=5,
        progress_total=5,
        error=None,
        started_at=NOW,
        finished_at=NOW,
    )
    return RunStatusEvent(cursor="1.sssss.s5", run=run)


def test_frame_has_id_event_and_data_lines():
    text = format_event(step_event())
    lines = text.split("\n")
    assert lines[0] == "id: 0.s.-"
    assert lines[1] == "event: step"
    assert lines[2].startswith("data: ")
    assert text.endswith("\n\n")
    payload = json.loads(lines[2][len("data: ") :])
    assert payload["type"] == "step"
    assert payload["cursor"] == "0.s.-"
    assert payload["step"]["position"] == 1


def test_event_names_follow_the_model_type():
    log = LogEvent(
        cursor="1..-",
        log=RunLogRead(id=1, run_id=5, logged_at=NOW, level="INFO", message="hello"),
    )
    assert "event: log\n" in format_event(log)
    assert "event: run\n" in format_event(run_event())


def test_frames_yield_bytes_in_order():
    chunks = list(frames([step_event(), run_event()]))
    assert all(isinstance(chunk, bytes) for chunk in chunks)
    assert chunks[0].startswith(b"id: 0.s.-")
    assert chunks[1].startswith(b"id: 1.sssss.s5")


def test_after_wins_over_last_event_id():
    assert resolve_cursor("a", "b") == "a"
    assert resolve_cursor(None, "b") == "b"
    assert resolve_cursor(None, None) is None
