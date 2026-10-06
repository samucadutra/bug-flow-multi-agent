"""The CLI as a child process against the stand-in and the compose database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from mocks.fake_openai_server import INVALID_KEY, VALID_KEY

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
BINARY = Path(sys.executable).parent / "bugflow"


@pytest.fixture
def cli(test_engine, stand_in):
    url = test_engine.url.render_as_string(hide_password=False)

    def run(*args, key=VALID_KEY):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "LOG_LEVEL"))
        }
        env.update(DATABASE_URL=url, OPENAI_BASE_URL=stand_in.base_url, TZ="UTC")
        if key is not None:
            env["OPENAI_API_KEY"] = key
        return subprocess.run(
            [str(BINARY), *args],
            cwd=BACKEND,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=120,
        )

    return run


def rows(engine, query):
    with engine.connect() as connection:
        return connection.execute(text(query)).all()


def test_help_lists_new_commands(cli):
    result = cli("--help")
    assert result.returncode == 0
    assert "index" in result.stdout and "search" in result.stdout


def test_index_twice(cli, seeded_db):
    first = cli("index")
    assert first.returncode == 0 and "Indexed 20/20 bugs" in first.stdout.splitlines()
    assert rows(seeded_db, "SELECT count(*) FROM bug_embeddings")[0][0] == 20
    run = rows(
        seeded_db,
        "SELECT status, progress_done, progress_total, started_at, finished_at, id "
        "FROM runs WHERE type = 'index'",
    )[0]
    assert run[:3] == ("succeeded", 20, 20) and run.started_at and run.finished_at
    assert rows(seeded_db, f"SELECT count(*) FROM run_logs WHERE run_id = {run.id}")[0][0] >= 1
    second = cli("index")
    assert second.returncode == 0 and "Indexed 20/20 bugs" in second.stdout.splitlines()
    assert rows(seeded_db, "SELECT count(*) FROM bug_embeddings")[0][0] == 20
    assert rows(seeded_db, "SELECT status FROM runs WHERE type = 'index'") == [("succeeded",)] * 2


def test_index_with_invalid_key(cli, seeded_db):
    result = cli("index", key=INVALID_KEY)
    assert result.returncode != 0 and "OpenAI authentication failed" in result.stderr
    assert INVALID_KEY not in result.stdout + result.stderr
    assert rows(seeded_db, "SELECT count(*) FROM bug_embeddings")[0][0] == 0
    assert rows(seeded_db, "SELECT status, error FROM runs WHERE type = 'index'") == [
        ("failed", "OpenAI authentication failed")
    ]


def test_index_without_key(cli, seeded_db, stand_in):
    result = cli("index", key=None)
    assert result.returncode != 0 and "OPENAI_API_KEY is not set" in result.stderr
    assert rows(seeded_db, "SELECT status, error FROM runs WHERE type = 'index'") == [
        ("failed", "OPENAI_API_KEY is not set")
    ]
    assert stand_in.embedding_requests() == []


def test_index_before_init(cli, fresh_schema, stand_in):
    result = cli("index")
    assert result.returncode != 0
    assert "Database schema is not initialized; run 'bugflow db init'" in result.stderr
    assert stand_in.embedding_requests() == []


def test_search_default_and_limits(cli, seed_indexed):
    default = cli("search", "button does nothing")
    lines = default.stdout.splitlines()
    assert default.returncode == 0 and lines[0] == "SCORE  ID  TITLE  STATUS" and len(lines) == 6
    scores = [float(line.split("  ")[0]) for line in lines[1:]]
    assert all(len(line.split("  ")[0].split(".")[1]) == 2 for line in lines[1:])
    assert scores == sorted(scores, reverse=True)
    maximum = cli("search", "button does nothing", "--limit", "20")
    assert maximum.returncode == 0 and len(maximum.stdout.splitlines()) == 21


def test_search_limit_21_rejected(cli, seed_indexed, stand_in):
    result = cli("search", "button does nothing", "--limit", "21")
    assert result.returncode != 0
    assert "Validation failed: limit: must be between 1 and 20" in result.stderr
    assert stand_in.embedding_requests() == []


def test_search_empty_text_rejected(cli, seeded_db):
    result = cli("search", "")
    assert result.returncode != 0 and "Search text must not be empty" in result.stderr


def test_search_before_indexing(cli, seeded_db, stand_in):
    result = cli("search", "button does nothing")
    assert result.returncode == 0
    assert "No bugs are indexed; run index" in result.stdout.splitlines()
    assert stand_in.embedding_requests() == []


def test_search_with_invalid_key(cli, seed_indexed):
    result = cli("search", "button does nothing", key=INVALID_KEY)
    assert result.returncode != 0 and "OpenAI authentication failed" in result.stderr
    assert INVALID_KEY not in result.stdout + result.stderr
