from datetime import UTC, datetime

import pytest

from bugflow.enums import RunStatus, RunType, StepStatus
from bugflow.services.errors import ValidationFailedError
from bugflow.services.run_events import (
    Cursor,
    derive_events,
    parse_cursor,
)
from bugflow.services.schemas import RunLogRead, RunRead, RunStepRead

NOW = datetime(2026, 10, 6, tzinfo=UTC)


def run(status="running", done=0):
    return RunRead(
        id=1,
        type=RunType.TRIAGE,
        bug_id=1,
        status=RunStatus(status),
        progress_done=done,
        progress_total=5,
        error=None,
        started_at=NOW,
        finished_at=None,
    )


def step(position, status, input=None):
    return RunStepRead(
        id=position,
        run_id=1,
        position=position,
        agent_key=f"a{position}",
        status=StepStatus(status),
        input=input,
        output=None,
        error=None,
        started_at=None,
        duration_ms=None,
    )


def log(log_id):
    return RunLogRead(id=log_id, run_id=1, logged_at=NOW, level="INFO", message=f"m{log_id}")


@pytest.mark.parametrize("text", ["0..-", "14.ssrpp.r2", "20.sssss.s5", "7.p.q0", "3..f1"])
def test_round_trip(text):
    assert parse_cursor(text).format() == text


def test_none_is_the_start():
    assert parse_cursor(None).format() == "0..-"


@pytest.mark.parametrize(
    "text", ["", "abc", "1.s", "1-s-r1", "-1..-", "1.x.r1", "1..x1", "1..r", "1..r1.", "a..-"]
)
def test_malformed_cursors(text):
    with pytest.raises(ValidationFailedError) as caught:
        parse_cursor(text)
    assert [(e.field, e.message) for e in caught.value.field_errors] == [
        ("after", "invalid cursor")
    ]


def test_full_derivation_order_and_cursors():
    steps = [step(i, "pending") for i in range(1, 4)]
    events = derive_events(run(), steps, [log(7), log(9)], Cursor())
    assert [e.type for e in events] == ["step"] * 3 + ["log"] * 2 + ["run"]
    assert [e.cursor for e in events] == [
        "0.p.-",
        "0.pp.-",
        "0.ppp.-",
        "7.ppp.-",
        "9.ppp.-",
        "9.ppp.r0",
    ]


def test_only_changed_steps_new_logs_and_changed_run():
    cursor = parse_cursor("7.ssp.r1")
    steps = [step(1, "succeeded"), step(2, "succeeded"), step(3, "running")]
    events = derive_events(run(done=1), steps, [log(7), log(8)], cursor)
    assert [e.type for e in events] == ["step", "log"]
    assert events[0].step.position == 3 and events[1].log.id == 8
    assert derive_events(run(done=1), steps, [], parse_cursor("8.ssr.r1")) == []


def test_run_event_on_progress_or_status_change():
    cursor = parse_cursor("0.s.r1")
    assert derive_events(run(done=1), [step(1, "succeeded")], [], cursor) == []
    assert derive_events(run(done=2), [step(1, "succeeded")], [], cursor)[0].type == "run"
    assert derive_events(run("failed", 1), [step(1, "succeeded")], [], cursor)[0].type == "run"


def test_resume_after_each_event_yields_the_rest():
    steps = [step(1, "succeeded"), step(2, "running"), step(3, "pending")]
    logs = [log(1), log(2)]
    full = derive_events(run(done=1), steps, logs, Cursor())
    for index, event in enumerate(full):
        rest = derive_events(run(done=1), steps, logs, parse_cursor(event.cursor))
        assert rest == full[index + 1 :]


def test_a_step_skipping_states_yields_one_event():
    cursor = parse_cursor("0.p.-")
    events = derive_events(run(), [step(1, "succeeded")], [], cursor)
    assert [e.step.status for e in events if e.type == "step"] == [StepStatus.SUCCEEDED]


def test_an_unchanged_status_with_a_new_input_is_not_an_event():
    cursor = parse_cursor("0.r.r0")
    assert derive_events(run(), [step(1, "running", input={"reask": 1})], [], cursor) == []


def test_steps_beyond_the_cursor_length_are_unseen():
    cursor = parse_cursor("0.s.r0")
    steps = [step(1, "succeeded"), step(2, "pending")]
    events = derive_events(run(), steps, [], cursor)
    assert [e.step.position for e in events] == [2] and events[0].cursor == "0.sp.r0"
