import pytest
from sqlalchemy import text

from bugflow.db.engine import session_factory
from bugflow.db.models import Bug, BugEmbedding, Run, RunLog, RunStep
from bugflow.services.db_admin import init_db, reset_db, seed_db

pytestmark = pytest.mark.integration

TABLES = [
    "bugs",
    "bug_embeddings",
    "component_classifications",
    "severity_classifications",
    "technical_analyses",
    "resolution_plans",
    "bug_reports",
    "runs",
    "run_steps",
    "run_logs",
]


def _count(engine, table: str) -> int:
    with engine.connect() as connection:
        return connection.execute(text(f'SELECT count(*) FROM "{table}"')).scalar_one()  # noqa: S608


@pytest.fixture
def populated(initialized_db):
    with session_factory(initialized_db)() as session:
        seed_db(session)
        bug_id = session.query(Bug.id).first()[0]
        run = Run(type="triage", status="queued")
        session.add(run)
        session.flush()
        session.add(RunStep(run_id=run.id, position=1, agent_key="ag1"))
        session.add(RunLog(run_id=run.id, level="INFO", message="hello"))
        session.add(BugEmbedding(bug_id=bug_id, embedding=[0.0] * 1536, text_hash="x" * 64))
        session.commit()
    return initialized_db


def test_removes_all_data(populated):
    reset_db(populated)
    for table in TABLES:
        assert _count(populated, table) == 0


def test_leaves_valid_schema(populated, schema_diff):
    result = reset_db(populated)
    with populated.connect() as connection:
        revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        extension = connection.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
        assert extension.first() is not None
    assert revision == result.current_revision == "0001"
    assert result.applied_revisions == ["0001"]
    assert schema_diff(populated) == []


def test_does_not_seed(populated):
    reset_db(populated)
    assert _count(populated, "bugs") == 0


def test_reset_on_fresh_initialized_db(initialized_db, schema_diff):
    reset_db(initialized_db)
    assert schema_diff(initialized_db) == []
    assert init_db(initialized_db).applied_revisions == []


def test_seed_works_after_reset(populated):
    reset_db(populated)
    assert _count(populated, "bugs") == 0
    with session_factory(populated)() as session:
        assert seed_db(session).created == 20
    assert _count(populated, "bugs") == 20
