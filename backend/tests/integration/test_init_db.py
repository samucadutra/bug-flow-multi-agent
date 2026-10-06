import logging
import shutil
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from bugflow import enums
from bugflow.db.errors import DatabaseUnavailableError, PgvectorUnavailableError
from bugflow.services import db_admin
from bugflow.services.db_admin import init_db

pytestmark = pytest.mark.integration

TABLES = {
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
}

ENUM_CHECKS = {
    "ck_bugs_environment": enums.Environment,
    "ck_bugs_reporting_team": enums.Team,
    "ck_bugs_status": enums.BugStatus,
    "ck_runs_type": enums.RunType,
    "ck_runs_status": enums.RunStatus,
    "ck_run_steps_status": enums.StepStatus,
    "ck_component_classifications_component": enums.Component,
    "ck_severity_classifications_severity": enums.Severity,
    "ck_resolution_plans_resolution_status": enums.ResolutionStatus,
    "ck_resolution_plans_assigned_team": enums.Team,
    "ck_resolution_plans_priority": enums.Priority,
}


def _tables(engine) -> set[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        return {row[0] for row in rows}


def test_creates_tables_and_extension(fresh_schema):
    result = init_db(fresh_schema)
    assert _tables(fresh_schema) == TABLES | {"alembic_version"}
    with fresh_schema.connect() as connection:
        extension = connection.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'"))
        assert extension.first() is not None
    assert result.applied_revisions
    assert result.current_revision == result.applied_revisions[-1]


def test_second_run_is_noop(fresh_schema, schema_snapshot):
    init_db(fresh_schema)
    before = schema_snapshot(fresh_schema)
    second = init_db(fresh_schema)
    assert second.applied_revisions == []
    assert schema_snapshot(fresh_schema) == before


def test_no_drift_between_models_and_migration(initialized_db, schema_diff):
    assert schema_diff(initialized_db) == []


def test_check_constraints_match_enum_module(initialized_db):
    with initialized_db.connect() as connection:
        rows = connection.execute(
            text("SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE contype = 'c'")
        )
        definitions = dict(rows.all())
    import re

    for name, enum_cls in ENUM_CHECKS.items():
        literals = re.findall(r"'([^']*)'", definitions[name])
        assert sorted(literals) == sorted(enums.codes(enum_cls)), name
    seniority = re.findall(r"'([^']*)'", definitions["ck_resolution_plans_assignee_seniority"])
    assert sorted(seniority[1:] if seniority[0] == "seniority" else seniority) == sorted(
        enums.codes(enums.Seniority)
    )


def test_pgvector_missing_fails_clearly(plain_engine):
    with pytest.raises(PgvectorUnavailableError) as info:
        init_db(plain_engine)
    assert str(info.value) == "pgvector extension is not available; use the pgvector/pgvector image"
    assert _tables(plain_engine) == set()


def test_unreachable_database_message(canary_db_password):
    url = f"postgresql+psycopg://bugflow:{canary_db_password}@127.0.0.1:1/bugflow"
    engine = create_engine(url)
    with pytest.raises(DatabaseUnavailableError) as info:
        init_db(engine)
    message = str(info.value)
    assert message == "Cannot connect to the database"
    assert canary_db_password not in message
    assert "127.0.0.1" not in message
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_failed_migration_rolls_back(fresh_schema, tmp_path: Path):
    source = Path(db_admin.MIGRATIONS_DIR)
    location = tmp_path / "migrations"
    (location / "versions").mkdir(parents=True)
    shutil.copy(source / "env.py", location / "env.py")
    shutil.copy(source / "script.py.mako", location / "script.py.mako")
    shutil.copy(source / "versions" / "0001_initial_schema.py", location / "versions")
    (location / "versions" / "0002_broken.py").write_text(
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        "revision = '0002'\n"
        "down_revision = '0001'\n"
        "branch_labels = None\n"
        "depends_on = None\n\n\n"
        "def upgrade():\n"
        "    op.create_table('extra_table', sa.Column('id', sa.Integer()))\n"
        "    op.execute('SELECT * FROM table_that_does_not_exist')\n\n\n"
        "def downgrade():\n"
        "    pass\n"
    )
    with pytest.raises(Exception, match="table_that_does_not_exist"):
        db_admin._upgrade(fresh_schema, location)
    assert _tables(fresh_schema) == set()


def test_init_logs_without_url(fresh_schema, caplog, canary_db_url):
    with caplog.at_level(logging.INFO, logger="bugflow.db"):
        result = init_db(fresh_schema)
    messages = [record.getMessage() for record in caplog.records]
    for revision in result.applied_revisions:
        assert any(revision in message for message in messages)
    assert all(canary_db_url not in message for message in messages)
    assert all("postgresql" not in message for message in messages)
