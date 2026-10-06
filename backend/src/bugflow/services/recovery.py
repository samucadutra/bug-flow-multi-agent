"""Startup recovery: fail interrupted runs and return stuck `processing` bugs to `failed`.

Call `recover_interrupted_runs` once at backend start, while no other process is executing
runs. All stored texts here are fixed strings.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, inspect, select, update
from sqlalchemy import func as sql_func
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from bugflow.db.engine import session_factory
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.db.models import Bug, Run, RunLog, RunStep
from bugflow.enums import BugStatus, RunStatus, StepStatus
from bugflow.logging_config import Redactor

logger = logging.getLogger(__name__)

INTERRUPTED_ERROR = "interrupted"
INTERRUPTED_LOG = "Run interrupted: the backend stopped before the run finished"
_UNFINISHED = (RunStatus.QUEUED.value, RunStatus.RUNNING.value)


class RecoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    interrupted_run_ids: list[int]
    recovered_bug_ids: list[int]


def close_open_steps(session: Session, run_id: int, error: str) -> None:
    """Set `running` steps of a run to `failed` with `error` and `pending` steps to `skipped`."""
    session.execute(
        update(RunStep)
        .where(RunStep.run_id == run_id, RunStep.status == StepStatus.RUNNING.value)
        .values(status=StepStatus.FAILED.value, error=error)
    )
    session.execute(
        update(RunStep)
        .where(RunStep.run_id == run_id, RunStep.status == StepStatus.PENDING.value)
        .values(status=StepStatus.SKIPPED.value)
    )


def recover_interrupted_runs(engine: Engine, redactor: Redactor | None = None) -> RecoveryResult:
    """Fail every `queued` or `running` run (`interrupted`) and free every `processing` bug."""
    redactor = redactor or Redactor()
    unreachable = False
    try:
        if not inspect(engine).has_table("runs"):
            return RecoveryResult(interrupted_run_ids=[], recovered_bug_ids=[])
        with session_factory(engine)() as session:
            run_ids = list(
                session.scalars(
                    select(Run.id)
                    .where(Run.status.in_(_UNFINISHED))
                    .order_by(Run.id)
                    .with_for_update()
                )
            )
            for run_id in run_ids:
                close_open_steps(session, run_id, INTERRUPTED_ERROR)
                session.add(
                    RunLog(run_id=run_id, level="ERROR", message=redactor.redact(INTERRUPTED_LOG))
                )
            if run_ids:
                session.execute(
                    update(Run)
                    .where(Run.id.in_(run_ids))
                    .values(
                        status=RunStatus.FAILED.value,
                        error=INTERRUPTED_ERROR,
                        finished_at=sql_func.clock_timestamp(),
                    )
                )
            bug_ids = list(
                session.scalars(
                    update(Bug)
                    .where(Bug.status == BugStatus.PROCESSING.value)
                    .values(status=BugStatus.FAILED.value, updated_at=sql_func.clock_timestamp())
                    .returning(Bug.id)
                )
            )
            session.commit()
    except (OperationalError, InterfaceError):
        unreachable = True
    if unreachable:
        raise DatabaseUnavailableError()
    bug_ids.sort()
    logger.info("Recovery: %d interrupted runs, %d recovered bugs", len(run_ids), len(bug_ids))
    return RecoveryResult(interrupted_run_ids=run_ids, recovered_bug_ids=bug_ids)
