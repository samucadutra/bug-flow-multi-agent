"""Database fixtures for integration tests. They use TEST_DATABASE_URL, never DATABASE_URL."""

from __future__ import annotations

import subprocess
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import psycopg
import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from psycopg import sql
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from bugflow.config import ConfigError, load_settings
from bugflow.db.base import Base
from bugflow.db.engine import create_db_engine, session_factory
from bugflow.db.models import Bug, Run
from bugflow.services.db_admin import init_db, seed_db
from bugflow.services.embeddings import index_all_bugs
from bugflow.services.llm_client import OpenAILlmClient
from mocks.fake_openai_server import VALID_KEY, FakeOpenAIServer
from tests_helpers import add_bug

ROOT = Path(__file__).resolve().parents[3]


def _test_url() -> str:
    try:
        url = load_settings().test_database_url
    except ConfigError:
        url = None
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; integration database tests are skipped")
    return url


def _ensure_database(url: str) -> None:
    parsed = make_url(url)
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": parsed.database}
            ).first()
            if exists is None:
                raw = connection.connection.driver_connection
                assert isinstance(raw, psycopg.Connection)
                raw.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(str(parsed.database)))
                )
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    url = _test_url()
    _ensure_database(url)
    engine = create_db_engine(url)
    yield engine
    engine.dispose()


def reset_public_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


@pytest.fixture
def fresh_schema(test_engine: Engine) -> Engine:
    """The test database with an empty `public` schema and no extension."""
    reset_public_schema(test_engine)
    return test_engine


@pytest.fixture
def initialized_db(fresh_schema: Engine) -> Engine:
    init_db(fresh_schema)
    return fresh_schema


@pytest.fixture
def session(initialized_db: Engine) -> Iterator[Session]:
    with session_factory(initialized_db)() as db_session:
        yield db_session


@pytest.fixture
def seeded_db(initialized_db: Engine) -> Engine:
    with session_factory(initialized_db)() as db_session:
        seed_db(db_session)
    return initialized_db


@pytest.fixture
def probe_bug(initialized_db: Engine) -> int:
    with session_factory(initialized_db)() as db_session:
        bug = Bug(
            title="probe-bug",
            description="Probe bug used as a parent row.",
            reproduction_steps="1. Run the constraint tests.",
            system_version="test 1.0.0",
            environment="testing",
            reporting_team="qa",
        )
        db_session.add(bug)
        db_session.commit()
        return bug.id


@pytest.fixture
def probe_run(initialized_db: Engine) -> int:
    with session_factory(initialized_db)() as db_session:
        run = Run(type="triage", status="queued")
        db_session.add(run)
        db_session.commit()
        return run.id


@pytest.fixture
def schema_snapshot() -> Callable[[Engine], dict[str, list[str]]]:
    def snapshot(engine: Engine) -> dict[str, list[str]]:
        with engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT table_name, column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
                )
            )
            result: dict[str, list[str]] = {}
            for table, column in rows:
                result.setdefault(table, []).append(column)
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            result["__revision__"] = [str(revision)]
            return result

    return snapshot


@pytest.fixture
def schema_diff() -> Callable[[Engine], list]:
    def diff(engine: Engine) -> list:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection, opts={"compare_type": True, "compare_server_default": False}
            )
            return compare_metadata(context, Base.metadata)

    return diff


@pytest.fixture
def plain_engine() -> Iterator[Engine]:
    """An engine for a Postgres server without pgvector, started from the compose profile."""
    import os
    import socket

    project = f"bugflow_plain_{uuid.uuid4().hex[:8]}"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]
    env = {**os.environ, "COMPOSE_PROJECT_NAME": project, "POSTGRES_PORT": str(free_port)}

    def compose(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", "--profile", "nopgvector", *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    try:
        compose("up", "-d", "--wait", "db_plain")
        address = compose("port", "db_plain", "5432").stdout.strip()
        port = address.rsplit(":", 1)[1]
        engine = create_db_engine(f"postgresql+psycopg://bugflow:bugflow@127.0.0.1:{port}/bugflow")
        yield engine
        engine.dispose()
    finally:
        subprocess.run(
            ["docker", "compose", "--profile", "nopgvector", "down", "-v"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )


@pytest.fixture
def probe_classification(initialized_db: Engine, probe_bug: int, probe_run: int) -> int:
    with initialized_db.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO component_classifications (bug_id, run_id, component, justification) "
                "VALUES (:bug_id, :run_id, 'backend', 'probe justification')"
            ),
            {"bug_id": probe_bug, "run_id": probe_run},
        )
    return probe_bug


# --- F04: OpenAI stand-in, LLM client and bug fixtures -----------------------------------------


@pytest.fixture
def stand_in() -> Iterator[FakeOpenAIServer]:
    server = FakeOpenAIServer().start()
    yield server
    server.stop()


@pytest.fixture
def make_llm_client(stand_in: FakeOpenAIServer) -> Callable[..., OpenAILlmClient]:
    def make(*, key: str = VALID_KEY, timeout: int = 60, retries: int = 2) -> OpenAILlmClient:
        return OpenAILlmClient(
            key,
            base_url=stand_in.base_url,
            timeout_seconds=timeout,
            max_retries=retries,
            embedding_model="text-embedding-3-small",
            chat_model="gpt-4o-mini",
            sleep=lambda _: None,
        )

    return make


@pytest.fixture
def llm_client(make_llm_client: Callable[..., OpenAILlmClient]) -> OpenAILlmClient:
    return make_llm_client()


TRIO = (
    ("Checkout button unresponsive", "Nothing happens when paying.", "Open the cart and pay.",
     "web 1.0.0", "production", "support"),
    ("Nightly report timeout", "The report query exceeds ten minutes.", "Run the nightly job.",
     "api 2.0.0", "staging", "data"),
    ("Checkout page layout broken", "Totals overlap on small screens.", "Resize the window.",
     "web 1.0.0", "production", "frontend"),
)  # fmt: skip


def add_bugs(engine: Engine, rows: list[tuple[str, str, str, str, str, str]]) -> list[int]:
    with session_factory(engine)() as db_session:
        bugs = [
            Bug(
                title=title,
                description=description,
                reproduction_steps=steps,
                system_version=version,
                environment=environment,
                reporting_team=team,
            )
            for title, description, steps, version, environment, team in rows
        ]
        db_session.add_all(bugs)
        db_session.commit()
        return [bug.id for bug in bugs]


@pytest.fixture
def trio(initialized_db: Engine) -> list[int]:
    """Ids of bugs A, B and C of the contract's `trio` state."""
    return add_bugs(initialized_db, list(TRIO))


@pytest.fixture
def trio_indexed(
    initialized_db: Engine, trio: list[int], llm_client: OpenAILlmClient, stand_in: FakeOpenAIServer
) -> list[int]:
    index_all_bugs(session_factory(initialized_db), llm_client)
    stand_in.reset()
    return trio


@pytest.fixture
def seed_indexed(
    seeded_db: Engine, llm_client: OpenAILlmClient, stand_in: FakeOpenAIServer
) -> Engine:
    index_all_bugs(session_factory(seeded_db), llm_client)
    stand_in.reset()
    return seeded_db


# --- F05: triage fixtures ---------------------------------------------------------------------


@pytest.fixture
def open_bug(initialized_db: Engine) -> int:
    """Handle `open-bug`: the only bug, `open`, no embedding, no result row."""
    return add_bug(initialized_db)


@pytest.fixture
def get_client(llm_client: OpenAILlmClient) -> Callable[[], OpenAILlmClient]:
    return lambda: llm_client


@pytest.fixture(autouse=True)
def _no_result_hooks() -> Iterator[None]:
    from bugflow.services.triage import clear_result_hooks

    clear_result_hooks()
    yield
    clear_result_hooks()
