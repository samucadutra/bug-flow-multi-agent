"""Run recorder: persists run progress and log lines incrementally.

Every `RunRecorder` call opens its own session and commits, so other connections see progress
at once. All stored text is redacted first. `DeferredRunRecorder` buffers in memory for
operations that run while the `runs` table does not exist yet (`init`) or is about to be wiped
(`reset`), and writes the run afterwards.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from bugflow.db.models import Run, RunLog
from bugflow.enums import RunStatus, RunType
from bugflow.logging_config import Redactor
from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.schemas import RunLogRead, RunRead

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
_FINISHED = (RunStatus.SUCCEEDED.value, RunStatus.FAILED.value)
_FINAL_STATUSES = (RunStatus.SUCCEEDED, RunStatus.FAILED)


def _check_level(level: str) -> str:
    upper = level.upper()
    if upper not in LOG_LEVELS:
        raise ValueError(f"Unknown log level: {level}")
    return upper


def _error_text(exc: BaseException, redactor: Redactor) -> str:
    return redactor.redact(str(exc) or type(exc).__name__)


class RunRecorder:
    """Writes run records; each method is its own short transaction."""

    def __init__(self, factory: sessionmaker[Session], redactor: Redactor | None = None) -> None:
        self._factory = factory
        self._redactor = redactor or Redactor()

    @property
    def redactor(self) -> Redactor:
        return self._redactor

    def _locked_status(self, session: Session, run_id: int) -> str:
        status = session.execute(
            select(Run.status).where(Run.id == run_id).with_for_update()
        ).scalar_one_or_none()
        if status is None:
            raise NotFoundError(f"Run {run_id} not found")
        return status

    def _locked_unfinished(self, session: Session, run_id: int) -> str:
        status = self._locked_status(session, run_id)
        if status in _FINISHED:
            raise StateConflictError(f"Run {run_id} is already finished")
        return status

    def create_run(self, run_type: RunType, bug_id: int | None = None, total: int = 0) -> int:
        with self._factory() as session:
            run = Run(
                type=RunType(run_type).value,
                bug_id=bug_id,
                status=RunStatus.QUEUED.value,
                progress_done=0,
                progress_total=total,
            )
            session.add(run)
            session.commit()
            return run.id

    def start_run(self, run_id: int) -> None:
        with self._factory() as session:
            status = self._locked_unfinished(session, run_id)
            if status != RunStatus.QUEUED.value:
                raise StateConflictError(f"Run {run_id} is already running")
            session.execute(
                Run.__table__.update()
                .where(Run.id == run_id)
                .values(status=RunStatus.RUNNING.value)
            )
            session.commit()

    def update_progress(self, run_id: int, done: int, total: int | None = None) -> None:
        values: dict[str, Any] = {"progress_done": done}
        if total is not None:
            values["progress_total"] = total
        with self._factory() as session:
            self._locked_unfinished(session, run_id)
            session.execute(Run.__table__.update().where(Run.id == run_id).values(**values))
            session.commit()

    def append_log(self, run_id: int, level: str, message: str) -> None:
        text = self._redactor.redact(message)
        with self._factory() as session:
            self._locked_unfinished(session, run_id)
            session.add(RunLog(run_id=run_id, level=_check_level(level), message=text))
            session.commit()

    def finish_run(self, run_id: int, status: RunStatus, error: str | None = None) -> None:
        status = RunStatus(status)
        if status not in _FINAL_STATUSES:
            raise ValueError("A run can only finish as succeeded or failed")
        stored_error = self._redactor.redact(error) if error is not None else None
        with self._factory() as session:
            self._locked_unfinished(session, run_id)
            session.execute(
                Run.__table__.update()
                .where(Run.id == run_id)
                .values(
                    status=status.value,
                    error=stored_error,
                    finished_at=func.clock_timestamp(),
                )
            )
            session.commit()

    def get_run(self, run_id: int) -> RunRead:
        with self._factory() as session:
            run = session.get(Run, run_id, populate_existing=True)
            if run is None:
                raise NotFoundError(f"Run {run_id} not found")
            return RunRead.model_validate(run, from_attributes=True)

    def get_run_logs(self, run_id: int) -> list[RunLogRead]:
        with self._factory() as session:
            if session.get(Run, run_id) is None:
                raise NotFoundError(f"Run {run_id} not found")
            rows = session.scalars(
                select(RunLog).where(RunLog.run_id == run_id).order_by(RunLog.id)
            )
            return [RunLogRead.model_validate(row, from_attributes=True) for row in rows]


@dataclass
class RunContext:
    """Handle given to the body of `recorded_run`."""

    run_id: int
    recorder: RunRecorder

    def log(self, level: str, message: str) -> None:
        self.recorder.append_log(self.run_id, level, message)

    def progress(self, done: int, total: int | None = None) -> None:
        self.recorder.update_progress(self.run_id, done, total)


@contextmanager
def recorded_run(
    recorder: RunRecorder, run_type: RunType, bug_id: int | None = None
) -> Iterator[RunContext]:
    """Create and start a run; finish it `succeeded` on exit, or `failed` before re-raising."""
    run_id = recorder.create_run(run_type, bug_id)
    recorder.start_run(run_id)
    try:
        yield RunContext(run_id, recorder)
    except BaseException as exc:
        recorder.finish_run(run_id, RunStatus.FAILED, _error_text(exc, recorder.redactor))
        raise
    recorder.finish_run(run_id, RunStatus.SUCCEEDED)


@dataclass(frozen=True)
class BufferedLog:
    logged_at: datetime
    level: str
    message: str


class DeferredRunRecorder:
    """Buffers a run in memory and writes it, with its original times, once the schema exists."""

    def __init__(
        self,
        run_type: RunType,
        redactor: Redactor | None = None,
        bug_id: int | None = None,
        total: int = 0,
    ) -> None:
        self.run_type = RunType(run_type)
        self.bug_id = bug_id
        self.started_at = datetime.now(UTC)
        self.progress_done = 0
        self.progress_total = total
        self.lines: list[BufferedLog] = []
        self._redactor = redactor or Redactor()

    def append_log(self, level: str, message: str) -> None:
        self.lines.append(
            BufferedLog(datetime.now(UTC), _check_level(level), self._redactor.redact(message))
        )

    def update_progress(self, done: int, total: int | None = None) -> None:
        self.progress_done = done
        if total is not None:
            self.progress_total = total

    def error_text(self, exc: BaseException) -> str:
        return _error_text(exc, self._redactor)

    def persist(
        self,
        factory: sessionmaker[Session],
        status: RunStatus,
        error: str | None = None,
    ) -> int:
        """Write the run and its log lines in one transaction and return the run id."""
        status = RunStatus(status)
        if status not in _FINAL_STATUSES:
            raise ValueError("A run can only be persisted as succeeded or failed")
        stored_error = self._redactor.redact(error) if error is not None else None
        with factory() as session:
            run = Run(
                type=self.run_type.value,
                bug_id=self.bug_id,
                status=status.value,
                progress_done=self.progress_done,
                progress_total=self.progress_total,
                error=stored_error,
                started_at=self.started_at,
                finished_at=datetime.now(UTC),
            )
            session.add(run)
            session.flush()
            session.add_all(
                RunLog(
                    run_id=run.id, logged_at=line.logged_at, level=line.level, message=line.message
                )
                for line in self.lines
            )
            session.commit()
            return run.id
