"""Run event source: steps, logs and run changes derived from persisted rows after a cursor.

Readers poll the database, so the same code serves runs started by this process, by another
process or by the CLI. The cursor is an opaque string `<log_id>.<steps>.<run>`:

- `log_id` is the decimal id of the last emitted log line (0 when none);
- `steps` has one character per step position, the last emitted status of that step
  (`-` never emitted, `p` pending, `r` running, `s` succeeded, `f` failed, `k` skipped);
- `run` is `-` (never emitted) or a status character (`q`, `r`, `s`, `f`) followed by the
  decimal `progress_done` last emitted.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, select
from sqlalchemy.exc import InterfaceError, OperationalError

from bugflow.db.engine import session_factory
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.db.models import Run, RunLog, RunStep
from bugflow.enums import RunStatus, StepStatus
from bugflow.services.errors import FieldError, NotFoundError, ValidationFailedError
from bugflow.services.schemas import RunLogRead, RunRead, RunStepRead

POLL_INTERVAL_SECONDS = 0.5
START_CURSOR = "0..-"

_STEP_CHARS = {
    StepStatus.PENDING: "p",
    StepStatus.RUNNING: "r",
    StepStatus.SUCCEEDED: "s",
    StepStatus.FAILED: "f",
    StepStatus.SKIPPED: "k",
}
_RUN_CHARS = {
    RunStatus.QUEUED: "q",
    RunStatus.RUNNING: "r",
    RunStatus.SUCCEEDED: "s",
    RunStatus.FAILED: "f",
}
_CURSOR_RE = re.compile(r"^(\d+)\.([-prskf]*)\.(-|[qrsf]\d+)$")
_FINAL = (RunStatus.SUCCEEDED, RunStatus.FAILED)


class StepEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["step"] = "step"
    cursor: str
    step: RunStepRead


class LogEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["log"] = "log"
    cursor: str
    log: RunLogRead


class RunStatusEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    type: Literal["run"] = "run"
    cursor: str
    run: RunRead


RunEvent = Annotated[StepEvent | LogEvent | RunStatusEvent, Field(discriminator="type")]


class EventPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    events: list[StepEvent | LogEvent | RunStatusEvent]
    cursor: str
    finished: bool


@dataclass(frozen=True)
class Cursor:
    log_id: int = 0
    steps: str = ""
    run: str = "-"

    def format(self) -> str:
        return f"{self.log_id}.{self.steps}.{self.run}"

    def step_char(self, position: int) -> str:
        return self.steps[position - 1] if position <= len(self.steps) else "-"

    def with_step(self, position: int, char: str) -> Cursor:
        padded = self.steps.ljust(position, "-")
        return Cursor(self.log_id, padded[: position - 1] + char + padded[position:], self.run)


def parse_cursor(text: str | None) -> Cursor:
    """Parse a cursor string; `None` is the start. Raises `ValidationFailedError`."""
    if text is None:
        return Cursor()
    match = _CURSOR_RE.match(text)
    if match is None:
        raise ValidationFailedError([FieldError(field="after", message="invalid cursor")])
    return Cursor(int(match.group(1)), match.group(2), match.group(3))


def derive_events(
    run: RunRead, steps: list[RunStepRead], logs: list[RunLogRead], cursor: Cursor
) -> list[StepEvent | LogEvent | RunStatusEvent]:
    """Events after `cursor`: changed steps, then new logs, then the run if it changed.

    Each event carries the cursor that resumes immediately after it.
    """
    events: list[StepEvent | LogEvent | RunStatusEvent] = []
    current = cursor
    for step in sorted(steps, key=lambda item: item.position):
        char = _STEP_CHARS[step.status]
        if current.step_char(step.position) != char:
            current = current.with_step(step.position, char)
            events.append(StepEvent(cursor=current.format(), step=step))
    for log in logs:
        if log.id > current.log_id:
            current = Cursor(log.id, current.steps, current.run)
            events.append(LogEvent(cursor=current.format(), log=log))
    marker = f"{_RUN_CHARS[run.status]}{run.progress_done}"
    if current.run != marker:
        current = Cursor(current.log_id, current.steps, marker)
        events.append(RunStatusEvent(cursor=current.format(), run=run))
    return events


def read_run_events(engine: Engine, run_id: int, after: str | None = None) -> EventPage:
    """One non-blocking read of the events of a run after the cursor `after`."""
    cursor = parse_cursor(after)
    unreachable = False
    try:
        with session_factory(engine)() as session:
            run_row = session.get(Run, run_id, populate_existing=True)
            if run_row is None:
                raise NotFoundError(f"Run {run_id} not found")
            run = RunRead.model_validate(run_row, from_attributes=True)
            steps = [
                RunStepRead.model_validate(row, from_attributes=True)
                for row in session.scalars(
                    select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.position)
                )
            ]
            logs = [
                RunLogRead.model_validate(row, from_attributes=True)
                for row in session.scalars(
                    select(RunLog)
                    .where(RunLog.run_id == run_id, RunLog.id > cursor.log_id)
                    .order_by(RunLog.id)
                )
            ]
    except (OperationalError, InterfaceError):
        unreachable = True
    if unreachable:
        raise DatabaseUnavailableError()
    events = derive_events(run, steps, logs, cursor)
    return EventPage(
        events=events,
        cursor=events[-1].cursor if events else cursor.format(),
        finished=run.status in _FINAL,
    )


def follow_pages(
    read_page: Callable[[str | None], EventPage],
    after: str | None,
    poll_interval: float,
    sleep: Callable[[float], None],
    first: EventPage | None = None,
) -> Iterator[StepEvent | LogEvent | RunStatusEvent]:
    """Yield the events of successive pages until a page reports the run finished."""
    page = first if first is not None else read_page(after)
    while True:
        yield from page.events
        if page.finished:
            return
        sleep(poll_interval)
        page = read_page(page.cursor)


def iter_run_events(
    engine: Engine,
    run_id: int,
    after: str | None = None,
    *,
    poll_interval: float = POLL_INTERVAL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[StepEvent | LogEvent | RunStatusEvent]:
    """Blocking generator of run events until the run is finished.

    The run and the cursor are validated at the call; no connection is held between polls.
    """
    first = read_run_events(engine, run_id, after)

    def read_page(cursor: str | None) -> EventPage:
        return read_run_events(engine, run_id, cursor)

    return follow_pages(read_page, after, poll_interval, sleep, first)
