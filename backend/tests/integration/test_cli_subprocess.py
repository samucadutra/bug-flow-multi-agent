import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
BINARY = Path(sys.executable).parent / "bugflow"
UNREACHABLE = "postgresql+psycopg://bugflow:s3cretpw@127.0.0.1:1/bugflow"
ABORTED = "Aborted: nothing was deleted"


@pytest.fixture
def cli(test_engine):
    url = test_engine.url.render_as_string(hide_password=False)

    def run(*args, stdin=subprocess.DEVNULL, input=None, database_url=url):
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "LOG_LEVEL"))
        }
        if database_url is not None:
            env["DATABASE_URL"] = database_url
        return subprocess.run(
            [str(BINARY), *args],
            cwd=BACKEND,
            env=env,
            input=input,
            stdin=None if input is not None else stdin,
            capture_output=True,
            text=True,
            timeout=120,
        )

    return run


def rows(engine, query):
    with engine.connect() as connection:
        return connection.execute(text(query)).all()


def test_help(cli):
    top = cli("--help")
    assert top.returncode == 0 and "check" in top.stdout and "db" in top.stdout
    sub = cli("db", "--help")
    assert sub.returncode == 0
    for name in ("init", "seed", "reset"):
        assert name in sub.stdout


def test_init_twice_records_runs(cli, fresh_schema):
    first = cli("db", "init")
    assert first.returncode == 0 and "Applied migration" in first.stdout
    (run,) = rows(fresh_schema, "SELECT type, status, started_at, finished_at, id FROM runs")
    assert run[:2] == ("init", "succeeded") and None not in run
    assert rows(fresh_schema, f"SELECT count(*) FROM run_logs WHERE run_id = {run.id}")[0][0] >= 1
    second = cli("db", "init")
    assert second.returncode == 0 and "Database schema is already up to date" in second.stdout
    assert (
        rows(fresh_schema, "SELECT type, status FROM runs ORDER BY id")
        == [("init", "succeeded")] * 2
    )


def test_seed_twice(cli, fresh_schema):
    assert cli("db", "init").returncode == 0
    first = cli("db", "seed")
    assert first.returncode == 0 and "Seeded 20 bugs" in first.stdout.splitlines()
    run = rows(
        fresh_schema,
        "SELECT status, progress_done, progress_total, finished_at, id FROM runs "
        "WHERE type = 'seed'",
    )[0]
    assert run[:3] == ("succeeded", 20, 20) and run.finished_at is not None
    assert rows(fresh_schema, f"SELECT count(*) FROM run_logs WHERE run_id = {run.id}")[0][0] >= 1
    again = cli("db", "seed")
    assert "20 bugs already present, nothing to do" in again.stdout.splitlines()
    assert rows(fresh_schema, "SELECT count(*) FROM bugs")[0][0] == 20


def test_seed_before_init(cli, fresh_schema):
    result = cli("db", "seed")
    assert result.returncode != 0
    assert "Database schema is not initialized; run 'bugflow db init'" in result.stderr
    assert rows(fresh_schema, "SELECT to_regclass('public.bugs')")[0][0] is None


@pytest.fixture
def seeded(cli, fresh_schema):
    assert cli("db", "init").returncode == 0 and cli("db", "seed").returncode == 0


def test_reset_with_yes_flag(cli, seeded, test_engine):
    result = cli("db", "reset", "--yes")
    assert result.returncode == 0
    assert "Database reset: schema recreated, no data loaded" in result.stdout.splitlines()
    assert rows(test_engine, "SELECT count(*) FROM bugs")[0][0] == 0
    (run,) = rows(test_engine, "SELECT type, status, started_at, finished_at, id FROM runs")
    assert run[:2] == ("reset", "succeeded") and None not in run
    assert rows(test_engine, f"SELECT count(*) FROM run_logs WHERE run_id = {run.id}")[0][0] >= 1


def test_reset_confirmed_by_typing(cli, seeded, test_engine):
    result = cli("db", "reset", input="yes\n")
    assert result.returncode == 0
    assert "This deletes all data. Type 'yes' to continue:" in result.stdout
    assert rows(test_engine, "SELECT count(*) FROM bugs")[0][0] == 0


@pytest.mark.parametrize("answer", ["no\n", None])
def test_reset_refused_or_unanswered(cli, seeded, test_engine, answer):
    result = cli("db", "reset", input=answer) if answer else cli("db", "reset")
    assert result.returncode == 1
    assert ABORTED in result.stdout + result.stderr
    assert rows(test_engine, "SELECT count(*) FROM bugs")[0][0] == 20
    assert rows(test_engine, "SELECT count(*) FROM runs WHERE type = 'reset'")[0][0] == 0


def test_check_without_key(cli, initialized_db):
    result = cli("check")
    assert result.stdout.splitlines() == [
        "database: ok",
        "vector search: ok",
        "llm: failed: OPENAI_API_KEY is not set",
    ]
    assert result.returncode == 1


def test_check_on_uninitialized_database(cli, fresh_schema):
    lines = cli("check").stdout.splitlines()
    assert lines[:2] == ["database: ok", "vector search: ok"] and lines[2].startswith(
        "llm: failed:"
    )


def test_check_unreachable_database(cli):
    result = cli("check", database_url=UNREACHABLE)
    assert result.stdout.splitlines() == [
        "database: failed: Cannot connect to the database",
        "vector search: failed: Database unreachable; vector search not checked",
        "llm: failed: OPENAI_API_KEY is not set",
    ]
    assert result.returncode == 1
    for stream in (result.stdout, result.stderr):
        assert "s3cretpw" not in stream and "127.0.0.1" not in stream


def test_init_unreachable_database(cli):
    result = cli("db", "init", database_url=UNREACHABLE)
    assert result.returncode != 0 and "Cannot connect to the database" in result.stderr
    for stream in (result.stdout, result.stderr):
        assert "s3cretpw" not in stream and "127.0.0.1" not in stream


def test_missing_database_url(cli):
    result = cli("db", "init", database_url=None)
    assert result.returncode != 0 and "DATABASE_URL is missing or invalid" in result.stderr
