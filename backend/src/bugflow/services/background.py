"""In-process background runner: queues triage, seed and index runs on two single-thread lanes.

`start_run` validates the request, claims the bug (triage), creates the `queued` run and queues
the work, then returns the run id(s) at once. The triage lane runs one triage at a time in
request order; the operations lane runs seed and index one at a time. Progress is visible only
through persisted rows (see `bugflow.services.run_events`).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, select, update
from sqlalchemy import func as sql_func
from sqlalchemy.exc import InterfaceError, OperationalError

from bugflow.agents.runtime import run_agent
from bugflow.db.engine import session_factory
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.db.models import Bug, Run
from bugflow.enums import BugStatus, RunStatus, RunType
from bugflow.logging_config import Redactor
from bugflow.services.errors import (
    FieldError,
    NotFoundError,
    SchemaNotInitializedError,
    StateConflictError,
    ValidationFailedError,
)
from bugflow.services.operations import is_schema_initialized, run_index, run_seed
from bugflow.services.recovery import close_open_steps
from bugflow.services.runs import RunRecorder
from bugflow.services.similarity import DEFAULT_SEARCH_LIMIT
from bugflow.services.triage import STEP_COUNT, Runner, claim_bug, execute_triage

logger = logging.getLogger(__name__)

UNEXPECTED_STEP_ERROR = "Run failed unexpectedly"
NOT_STARTED_ERROR = "not started"


class RunKind(StrEnum):
    TRIAGE = "triage"
    INDEX = "index"
    SEED = "seed"


class StartResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_ids: list[int]

    @property
    def run_id(self) -> int:
        """The only run id; raises `ValueError` when there is not exactly one."""
        if len(self.run_ids) != 1:
            raise ValueError("The result does not hold exactly one run id")
        return self.run_ids[0]


@dataclass(frozen=True)
class RunRequest:
    """A validated request: `bug_id` for one triage, `all_open` for the batch."""

    kind: RunKind
    bug_id: int | None = None
    all_open: bool = False


def _fail(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError([FieldError(field=field, message=message)])


def parse_request(kind: str, params: Mapping[str, Any] | None = None) -> RunRequest:
    """Validate a start request without touching the database."""
    try:
        run_kind = RunKind(kind)
    except ValueError:
        raise _fail("kind", "must be one of triage, index, seed") from None
    values = dict(params or {})
    if run_kind != RunKind.TRIAGE:
        if values:
            raise _fail("params", "must be empty")
        return RunRequest(run_kind)
    errors: list[FieldError] = []
    for key in values:
        if key not in ("bug_id", "all"):
            errors.append(FieldError(field=key, message="is not allowed"))
    if "bug_id" in values:
        bug_id = values["bug_id"]
        if not isinstance(bug_id, int) or isinstance(bug_id, bool):
            errors.append(FieldError(field="bug_id", message="must be an integer"))
    if "all" in values and not isinstance(values["all"], bool):
        errors.append(FieldError(field="all", message="must be a boolean"))
    if errors:
        raise ValidationFailedError(errors)
    wants_all = values.get("all") is True
    if ("bug_id" in values) == wants_all:
        raise _fail("params", "Specify exactly one of bug_id or all")
    if wants_all:
        return RunRequest(run_kind, all_open=True)
    return RunRequest(run_kind, bug_id=values["bug_id"])


_STOP = object()


class Lane:
    """One daemon thread executing submitted tasks in FIFO order, one at a time."""

    def __init__(self, name: str) -> None:
        self.name = name
        self._queue: queue.Queue[Any] = queue.Queue()
        self._condition = threading.Condition()
        self._pending = 0
        self._closed = False
        self._thread: threading.Thread | None = None

    @property
    def thread(self) -> threading.Thread | None:
        return self._thread

    def submit(
        self, task: Callable[[], None], on_error: Callable[[Exception], None] | None = None
    ) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeError("The lane is shut down")
            self._pending += 1
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name=self.name, daemon=True)
                self._thread.start()
            self._queue.put((task, on_error))

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _STOP:
                return
            task, on_error = item
            try:
                task()
            except Exception as exc:
                if on_error is not None:
                    try:
                        on_error(exc)
                    except Exception as cleanup_exc:
                        logger.warning("Lane %s cleanup failed: %s", self.name, cleanup_exc)
            finally:
                with self._condition:
                    self._pending -= 1
                    self._condition.notify_all()

    def wait_idle(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while self._pending > 0:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def shutdown(self, timeout: float | None = None) -> None:
        with self._condition:
            self._closed = True
            dropped = 0
            while True:
                try:
                    item = self._queue.get_nowait()
                except queue.Empty:
                    break
                if item is not _STOP:
                    dropped += 1
            self._pending -= dropped
            self._condition.notify_all()
            thread = self._thread
            if thread is not None:
                self._queue.put(_STOP)
        if thread is not None:
            thread.join(timeout)


class BackgroundRunner:
    """Starts runs and executes them on the triage and operations lanes."""

    def __init__(
        self,
        engine: Engine,
        get_client: Callable[[], Any],
        redactor: Redactor | None = None,
        *,
        similar_k: int = DEFAULT_SEARCH_LIMIT,
        agent_runner: Runner = run_agent,
    ) -> None:
        self._engine = engine
        self._factory = session_factory(engine)
        self._get_client = get_client
        self._redactor = redactor or Redactor()
        self._similar_k = similar_k
        self._agent_runner = agent_runner
        self._recorder = RunRecorder(self._factory, self._redactor)
        self._triage_lane = Lane("bugflow-triage-lane")
        self._operations_lane = Lane("bugflow-operations-lane")
        self._closed = False

    # --- public API ----------------------------------------------------------------------------

    def start_run(self, kind: str, params: Mapping[str, Any] | None = None) -> StartResult:
        """Validate, create the queued run(s), queue the work and return the run id(s)."""
        request = parse_request(kind, params)
        if self._closed:
            raise RuntimeError("The runner is shut down")
        if request.kind == RunKind.TRIAGE:
            if request.all_open:
                return StartResult(run_ids=self._start_triage_all())
            assert request.bug_id is not None
            return StartResult(run_ids=[self._start_triage(request.bug_id)])
        return StartResult(run_ids=[self._start_operation(request.kind)])

    def wait_idle(self, timeout: float | None = None) -> bool:
        """True when both lanes are empty and idle."""
        deadline = None if timeout is None else time.monotonic() + timeout
        for lane in (self._triage_lane, self._operations_lane):
            remaining = None if deadline is None else max(deadline - time.monotonic(), 0.0)
            if not lane.wait_idle(remaining):
                return False
        return True

    def shutdown(self, timeout: float | None = None) -> None:
        """Stop accepting work; the running item finishes and queued items are dropped."""
        self._closed = True
        for lane in (self._triage_lane, self._operations_lane):
            lane.shutdown(timeout)

    # --- start helpers (caller thread) ---------------------------------------------------------

    def _create_triage_run(self, bug_id: int) -> int:
        """Create the queued run of a claimed bug; on failure the bug returns to `failed`."""
        try:
            return self._recorder.create_run(RunType.TRIAGE, bug_id, STEP_COUNT)
        except Exception as exc:
            unreachable = isinstance(exc, OperationalError | InterfaceError)
            self._release_bug(bug_id)
            if unreachable:
                raise DatabaseUnavailableError() from None
            raise

    def _start_triage(self, bug_id: int) -> int:
        claim_bug(self._engine, bug_id)
        run_id = self._create_triage_run(bug_id)
        self._queue_triage(run_id, bug_id)
        return run_id

    def _start_triage_all(self) -> list[int]:
        unreachable = False
        try:
            with self._factory() as session:
                ids = list(
                    session.scalars(
                        select(Bug.id).where(Bug.status == BugStatus.OPEN.value).order_by(Bug.id)
                    )
                )
        except (OperationalError, InterfaceError):
            unreachable = True
        if unreachable:
            raise DatabaseUnavailableError()
        prepared: list[tuple[int, int]] = []
        try:
            for bug_id in ids:
                try:
                    claim_bug(self._engine, bug_id)
                except (StateConflictError, NotFoundError):
                    logger.info("Bug %s was claimed elsewhere or removed; skipped", bug_id)
                    continue
                prepared.append((self._create_triage_run(bug_id), bug_id))
        except Exception:
            for run_id, bug_id in prepared:
                self._finish_unfinished(run_id, NOT_STARTED_ERROR)
                self._release_bug(bug_id)
            raise
        for run_id, bug_id in prepared:
            self._queue_triage(run_id, bug_id)
        return [run_id for run_id, _ in prepared]

    def _queue_triage(self, run_id: int, bug_id: int) -> None:
        def task() -> None:
            execute_triage(
                self._engine,
                self._get_client,
                bug_id,
                run_id,
                self._redactor,
                similar_k=self._similar_k,
                runner=self._agent_runner,
            )

        self._triage_lane.submit(task, lambda exc: self._safety_net(run_id, bug_id, exc))

    def _start_operation(self, kind: RunKind) -> int:
        if not is_schema_initialized(self._engine):
            raise SchemaNotInitializedError()
        run_type = RunType(kind.value)
        try:
            run_id = self._recorder.create_run(run_type)
        except (OperationalError, InterfaceError):
            raise DatabaseUnavailableError() from None

        def task() -> None:
            if kind == RunKind.SEED:
                run_seed(self._engine, self._redactor, run_id=run_id)
            else:
                run_index(self._engine, self._get_client, self._redactor, run_id=run_id)

        self._operations_lane.submit(task, lambda exc: self._safety_net(run_id, None, exc))
        return run_id

    # --- failure containment -------------------------------------------------------------------

    def _release_bug(self, bug_id: int) -> None:
        """Best effort: a `processing` bug returns to `failed` (conditional update)."""
        try:
            with self._factory() as session:
                session.execute(
                    update(Bug)
                    .where(Bug.id == bug_id, Bug.status == BugStatus.PROCESSING.value)
                    .values(status=BugStatus.FAILED.value, updated_at=sql_func.clock_timestamp())
                )
                session.commit()
        except Exception as exc:
            logger.warning("Could not release bug %s: %s", bug_id, type(exc).__name__)

    def _finish_unfinished(self, run_id: int, error: str) -> None:
        """Best effort: finish a `queued` or `running` run as `failed`."""
        try:
            with self._factory() as session:
                status = session.scalar(select(Run.status).where(Run.id == run_id))
            if status in (RunStatus.QUEUED.value, RunStatus.RUNNING.value):
                self._recorder.finish_run(run_id, RunStatus.FAILED, error)
        except Exception as exc:
            logger.warning("Could not finish run %s: %s", run_id, type(exc).__name__)

    def _safety_net(self, run_id: int, bug_id: int | None, exc: Exception) -> None:
        """After a task raised: finish the run, close its steps and free its bug."""
        text = self._redactor.redact(str(exc) or type(exc).__name__)
        logger.warning("Run %s failed with an unexpected error: %s", run_id, text)
        self._finish_unfinished(run_id, text)
        try:
            with self._factory() as session:
                close_open_steps(session, run_id, UNEXPECTED_STEP_ERROR)
                session.commit()
        except Exception as cleanup_exc:
            logger.warning(
                "Could not close steps of run %s: %s", run_id, type(cleanup_exc).__name__
            )
        if bug_id is not None:
            self._release_bug(bug_id)
