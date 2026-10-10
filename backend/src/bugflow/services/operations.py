"""Recorded administrative operations: `run_init`, `run_seed` and `run_reset`.

Each wraps an F02 service and persists a run record with status, timestamps and log lines.
"""

from __future__ import annotations

from collections.abc import Callable

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import InterfaceError, OperationalError

from bugflow.db.engine import session_factory
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.db.models import Bug
from bugflow.enums import RunStatus, RunType
from bugflow.logging_config import Redactor
from bugflow.seed.bugs import SEED_BUGS
from bugflow.services.db_admin import (
    MIGRATIONS_DIR,
    InitResult,
    SeedResult,
    init_db,
    reset_db,
    seed_db,
)
from bugflow.services.embeddings import EmbeddingClient, IndexResult, index_all_bugs
from bugflow.services.errors import SchemaNotInitializedError
from bugflow.services.runs import DeferredRunRecorder, RunRecorder, recorded_run


def init_messages(result: InitResult) -> list[str]:
    """One line per applied revision, or the up-to-date line."""
    if not result.applied_revisions:
        return ["Database schema is already up to date"]
    return [f"Applied migration {revision}" for revision in result.applied_revisions]


def seed_message(result: SeedResult) -> str:
    if result.created == 0:
        return f"{result.already_present} bugs already present, nothing to do"
    if result.already_present == 0:
        return f"Seeded {result.created} bugs"
    return f"Seeded {result.created} bugs ({result.already_present} already present)"


def is_schema_initialized(engine: Engine) -> bool:
    """True when the database revision equals the migration head."""
    head = ScriptDirectory(str(MIGRATIONS_DIR)).get_current_head()
    unreachable = False
    current: str | None = None
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    except (OperationalError, InterfaceError):
        unreachable = True
    if unreachable:
        raise DatabaseUnavailableError()
    return current is not None and current == head


def _runs_table_exists(engine: Engine) -> bool:
    try:
        return inspect(engine).has_table("runs")
    except Exception:
        return False


def _deferred(
    engine: Engine,
    run_type: RunType,
    redactor: Redactor | None,
    operation: Callable[[Engine], InitResult],
) -> InitResult:
    recorder = DeferredRunRecorder(run_type, redactor)
    try:
        result = operation(engine)
    except Exception as exc:
        # An unreachable database or a missing `runs` table means there is nowhere to record.
        if _runs_table_exists(engine):
            recorder.persist(session_factory(engine), RunStatus.FAILED, recorder.error_text(exc))
        raise
    for line in init_messages(result):
        recorder.append_log("INFO", line)
    count = len(result.applied_revisions)
    recorder.update_progress(count, count)
    recorder.persist(session_factory(engine), RunStatus.SUCCEEDED)
    return result


def run_init(engine: Engine, redactor: Redactor | None = None) -> InitResult:
    """Apply pending migrations and record an `init` run once the schema exists."""
    return _deferred(engine, RunType.INIT, redactor, init_db)


def run_reset(engine: Engine, redactor: Redactor | None = None) -> InitResult:
    """Recreate the schema without data and record a `reset` run in the new schema."""
    return _deferred(engine, RunType.RESET, redactor, reset_db)


def run_seed(
    engine: Engine, redactor: Redactor | None = None, *, run_id: int | None = None
) -> SeedResult:
    """Load the seed bugs into an initialized schema and record a `seed` run.

    With `run_id`, the given `queued` run is used instead of creating a new one.
    """
    if not is_schema_initialized(engine):
        raise SchemaNotInitializedError()
    factory = session_factory(engine)
    recorder = RunRecorder(factory, redactor)
    total = len(SEED_BUGS)
    with recorded_run(recorder, RunType.SEED, run_id=run_id) as run:
        run.progress(0, total)
        with factory() as session:
            result = seed_db(session)
        run.log("INFO", seed_message(result))
        run.progress(result.created + result.already_present, total)
    return result


def index_message(result: IndexResult) -> str:
    return f"Indexed {result.indexed}/{result.total} bugs"


def run_index(
    engine: Engine,
    get_client: Callable[[], EmbeddingClient],
    redactor: Redactor | None = None,
    *,
    run_id: int | None = None,
) -> IndexResult:
    """Rebuild every bug embedding inside a recorded `index` run.

    With `run_id`, the given `queued` run is used instead of creating a new one.

    The client is built inside the run, so a missing key fails the run and is recorded.
    """
    if not is_schema_initialized(engine):
        raise SchemaNotInitializedError()
    factory = session_factory(engine)
    recorder = RunRecorder(factory, redactor)
    with recorded_run(recorder, RunType.INDEX, run_id=run_id) as run:
        with factory() as session:
            total = session.scalar(select(func.count()).select_from(Bug)) or 0
        run.progress(0, total)
        client = get_client()

        def on_batch(done: int, total: int, number: int, count: int, size: int) -> None:
            run.progress(done, total)
            run.log("INFO", f"Embedded batch {number} of {count} ({size} bugs)")

        result = index_all_bugs(factory, client, on_batch)
        if result.total == 0:
            run.log("INFO", "No bugs to index")
        run.progress(result.indexed, result.total)
    return result
