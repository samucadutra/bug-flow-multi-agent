import pytest
from sqlalchemy import text

from bugflow.db.engine import create_db_engine
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.services import operations
from bugflow.services.errors import SchemaNotInitializedError
from bugflow.services.operations import run_init, run_reset, run_seed

pytestmark = pytest.mark.integration


def runs(engine, run_type=None):
    query = (
        "SELECT id, type, status, progress_done, progress_total, error, started_at, finished_at "
        "FROM runs"
    )
    with engine.connect() as connection:
        rows = connection.execute(text(query + " ORDER BY id")).all()
    return [row for row in rows if run_type in (None, row.type)]


def logs(engine, run_id):
    with engine.connect() as connection:
        return [
            row[0]
            for row in connection.execute(
                text("SELECT message FROM run_logs WHERE run_id = :id ORDER BY id"), {"id": run_id}
            )
        ]


def count(engine, table):
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table}")).scalar()  # noqa: S608


def test_run_init_on_empty_database(fresh_schema):
    result = run_init(fresh_schema)
    (run,) = runs(fresh_schema)
    assert run.type == "init" and run.status == "succeeded"
    assert run.started_at is not None and run.finished_at >= run.started_at
    assert (run.progress_done, run.progress_total) == (len(result.applied_revisions),) * 2
    assert logs(fresh_schema, run.id) == [
        f"Applied migration {r}" for r in result.applied_revisions
    ]


def test_second_init_records_up_to_date_run(fresh_schema):
    run_init(fresh_schema)
    run_init(fresh_schema)
    rows = runs(fresh_schema, "init")
    assert [row.status for row in rows] == ["succeeded", "succeeded"]
    assert logs(fresh_schema, rows[1].id) == ["Database schema is already up to date"]


def test_seed_before_init_raises_and_creates_nothing(fresh_schema):
    with pytest.raises(SchemaNotInitializedError) as caught:
        run_seed(fresh_schema)
    assert caught.value.message == "Database schema is not initialized; run 'bugflow db init'"
    with fresh_schema.connect() as connection:
        assert connection.execute(text("SELECT to_regclass('public.bugs')")).scalar() is None


def test_run_seed_records_progress_and_messages(initialized_db):
    assert run_seed(initialized_db).created == 20
    (run,) = runs(initialized_db, "seed")
    assert run.status == "succeeded" and (run.progress_done, run.progress_total) == (20, 20)
    assert logs(initialized_db, run.id) == ["Seeded 20 bugs"]
    assert run_seed(initialized_db).already_present == 20
    again = runs(initialized_db, "seed")[1]
    assert logs(initialized_db, again.id) == ["20 bugs already present, nothing to do"]
    assert count(initialized_db, "bugs") == 20


def test_run_reset_leaves_exactly_one_reset_run(seeded_db):
    run_seed(seeded_db)
    run_reset(seeded_db)
    rows = runs(seeded_db)
    assert [row.type for row in rows] == ["reset"] and rows[0].status == "succeeded"
    assert count(seeded_db, "bugs") == 0
    assert logs(seeded_db, rows[0].id)


def test_failing_seed_records_redacted_failure(initialized_db, monkeypatch, canary_api_key):
    def broken(session):
        raise RuntimeError(f"seed exploded {canary_api_key}")

    monkeypatch.setattr(operations, "seed_db", broken)
    from bugflow.logging_config import Redactor

    with pytest.raises(RuntimeError):
        run_seed(initialized_db, Redactor([canary_api_key]))
    (run,) = runs(initialized_db, "seed")
    assert run.status == "failed" and run.error == "seed exploded ***"


def test_unreachable_database_records_nothing(canary_db_password):
    engine = create_db_engine(
        f"postgresql+psycopg://bugflow:{canary_db_password}@127.0.0.1:1/bugflow"
    )
    for operation in (run_init, run_reset, run_seed):
        with pytest.raises(DatabaseUnavailableError) as caught:
            operation(engine)
        assert canary_db_password not in str(caught.value)
