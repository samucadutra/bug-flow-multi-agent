"""Run read models: recent runs, the runs of a bug and the detail of one run."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from bugflow.db.models import Bug, Run, RunLog, RunStep
from bugflow.enums import RunStatus, RunType
from bugflow.services.errors import NotFoundError
from bugflow.services.schemas import RunLogRead, RunRead, RunStepRead

DEFAULT_RUN_LIMIT = 10
MIN_RUN_LIMIT = 1
MAX_RUN_LIMIT = 100


class RunDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: RunRead
    steps: list[RunStepRead]
    logs: list[RunLogRead]


def _read(rows) -> list[RunRead]:
    return [RunRead.model_validate(row, from_attributes=True) for row in rows]


def list_runs(
    session: Session,
    run_type: RunType | None = None,
    status: RunStatus | None = None,
    limit: int = DEFAULT_RUN_LIMIT,
) -> list[RunRead]:
    """Recent runs, newest first by start time then id."""
    statement = select(Run).order_by(Run.started_at.desc(), Run.id.desc()).limit(limit)
    if run_type is not None:
        statement = statement.where(Run.type == run_type.value)
    if status is not None:
        statement = statement.where(Run.status == status.value)
    return _read(session.scalars(statement))


def list_bug_runs(session: Session, bug_id: int) -> list[RunRead]:
    """Every run of the bug, newest first. Raises `NotFoundError` for an unknown bug."""
    if session.get(Bug, bug_id) is None:
        raise NotFoundError(f"Bug {bug_id} not found")
    statement = (
        select(Run).where(Run.bug_id == bug_id).order_by(Run.started_at.desc(), Run.id.desc())
    )
    return _read(session.scalars(statement))


def get_run_detail(session: Session, run_id: int) -> RunDetail:
    """The run with its steps (by position) and logs (by id)."""
    run = session.get(Run, run_id, populate_existing=True)
    if run is None:
        raise NotFoundError(f"Run {run_id} not found")
    steps = session.scalars(
        select(RunStep).where(RunStep.run_id == run_id).order_by(RunStep.position)
    )
    logs = session.scalars(select(RunLog).where(RunLog.run_id == run_id).order_by(RunLog.id))
    return RunDetail(
        run=RunRead.model_validate(run, from_attributes=True),
        steps=[RunStepRead.model_validate(row, from_attributes=True) for row in steps],
        logs=[RunLogRead.model_validate(row, from_attributes=True) for row in logs],
    )
