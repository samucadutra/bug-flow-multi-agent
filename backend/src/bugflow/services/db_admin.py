"""Database administration services: `init_db`, `seed_db` and `reset_db`."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Connection, Engine, select, text
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from bugflow.db.base import Base, version_table
from bugflow.db.errors import DatabaseUnavailableError, PgvectorUnavailableError
from bugflow.db.models import Bug
from bugflow.logging_config import get_logger
from bugflow.seed.bugs import SEED_BUGS, SEED_STATUS

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

logger = get_logger("bugflow.db")


class InitResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    applied_revisions: list[str]
    current_revision: str


class SeedResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    created: int
    already_present: int


def _alembic_config(connection: Connection, script_location: Path) -> Config:
    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.attributes["connection"] = connection
    return config


def _check_server(engine: Engine) -> None:
    """Fail clearly when the server is unreachable or lacks the `vector` extension."""
    unreachable = False
    has_vector = False
    try:
        with engine.connect() as connection:
            has_vector = (
                connection.execute(
                    text("SELECT 1 FROM pg_available_extensions WHERE name = :name"),
                    {"name": "vector"},
                ).first()
                is not None
            )
    except (OperationalError, InterfaceError):
        unreachable = True
    # Raised outside the except block so no driver exception (and no URL) is chained.
    if unreachable:
        raise DatabaseUnavailableError()
    if not has_vector:
        raise PgvectorUnavailableError()


def _pending_revisions(script: ScriptDirectory, current: str | None) -> list[str]:
    head = script.get_current_head()
    if head is None or head == current:
        return []
    revisions = [rev.revision for rev in script.iterate_revisions(head, current or "base")]
    revisions.reverse()
    return [rev for rev in revisions if rev != current]


def _upgrade(engine: Engine, script_location: Path) -> InitResult:
    applied: list[str] = []
    with engine.begin() as connection:
        config = _alembic_config(connection, script_location)
        script = ScriptDirectory.from_config(config)
        current = MigrationContext.configure(connection).get_current_revision()
        applied = _pending_revisions(script, current)
        if applied:
            command.upgrade(config, "head")
        head = script.get_current_head() or ""
    for revision in applied:
        logger.info("Applied migration %s", revision)
    if not applied:
        logger.info("Database schema is already up to date (revision %s)", head)
    return InitResult(applied_revisions=applied, current_revision=head)


def init_db(engine: Engine) -> InitResult:
    """Apply every pending migration. Idempotent."""
    _check_server(engine)
    return _upgrade(engine, MIGRATIONS_DIR)


def seed_db(session: Session) -> SeedResult:
    """Insert the packaged seed bugs that are missing (matched by title) in one transaction."""
    try:
        titles = [seed.title for seed in SEED_BUGS]
        existing = set(session.scalars(select(Bug.title).where(Bug.title.in_(titles))))
        missing = [seed for seed in SEED_BUGS if seed.title not in existing]
        session.add_all(
            Bug(
                title=seed.title,
                description=seed.description,
                reproduction_steps=seed.reproduction_steps,
                system_version=seed.system_version,
                environment=seed.environment,
                reporting_team=seed.reporting_team,
                status=SEED_STATUS,
                opened_at=seed.opened_at,
            )
            for seed in missing
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    result = SeedResult(created=len(missing), already_present=len(SEED_BUGS) - len(missing))
    logger.info(
        "Seed finished: %d created, %d already present", result.created, result.already_present
    )
    return result


def reset_db(engine: Engine) -> InitResult:
    """Drop every application table and `alembic_version`, keep the extension, then init."""
    _check_server(engine)
    with engine.begin() as connection:
        Base.metadata.drop_all(connection)
        logger.info("Dropped application tables")
        version_table().drop(connection, checkfirst=True)
        logger.info("Dropped migration bookkeeping table")
    return init_db(engine)
