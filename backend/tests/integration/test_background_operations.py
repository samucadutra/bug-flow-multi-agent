import time

import pytest
from sqlalchemy import text

from mocks.fake_openai_server import INVALID_KEY, default_reply
from tests_helpers import add_bug, log_rows, run_row, wait_final

pytestmark = pytest.mark.integration


def count(engine, table):
    with engine.connect() as connection:
        return connection.execute(text(f"SELECT count(*) FROM {table}")).scalar()  # noqa: S608


def test_seed_runs_in_the_background(runner, initialized_db):
    run_id = runner.start_run("seed", {}).run_id
    row = wait_final(initialized_db, run_id)
    assert (row.type, row.status, row.progress_done, row.progress_total) == (
        "seed",
        "succeeded",
        20,
        20,
    )
    with initialized_db.connect() as connection:
        statuses = connection.execute(text("SELECT DISTINCT status FROM bugs")).all()
    assert count(initialized_db, "bugs") == 20 and [s[0] for s in statuses] == ["open"]
    assert "Seeded 20 bugs" in [line.message for line in log_rows(initialized_db, run_id)]


def test_index_runs_in_the_background(runner, seeded_db):
    run_id = runner.start_run("index", {}).run_id
    row = wait_final(seeded_db, run_id)
    assert (row.type, row.status, row.progress_done, row.progress_total) == (
        "index",
        "succeeded",
        20,
        20,
    )
    assert count(seeded_db, "bug_embeddings") == 20
    assert any(line.message.startswith("Embedded batch") for line in log_rows(seeded_db, run_id))


def test_a_missing_key_fails_the_index_run(make_runner, no_key_factory, seeded_db, stand_in):
    runner = make_runner(no_key_factory)
    run_id = runner.start_run("index", {}).run_id
    row = wait_final(seeded_db, run_id)
    assert (row.status, row.error) == ("failed", "OPENAI_API_KEY is not set")
    assert count(seeded_db, "bug_embeddings") == 0
    assert stand_in.requests == []


def test_an_invalid_key_fails_without_leaking_it(make_runner, make_llm_client, seeded_db):
    runner = make_runner(lambda: make_llm_client(key=INVALID_KEY))
    run_id = runner.start_run("index", {}).run_id
    row = wait_final(seeded_db, run_id)
    assert (row.status, row.error) == ("failed", "OpenAI authentication failed")
    assert count(seeded_db, "bug_embeddings") == 0
    assert INVALID_KEY not in (row.error or "")
    assert all(INVALID_KEY not in line.message for line in log_rows(seeded_db, run_id))


def test_triage_and_operations_lanes_are_independent(runner, initialized_db, stand_in):
    bug_id = add_bug(initialized_db)
    stand_in.script_chat(
        [
            {
                "role": "Component Classifier",
                "json": default_reply("Component Classifier"),
                "delay": 6,
            }
        ]
    )
    triage_id = runner.start_run("triage", {"bug_id": bug_id}).run_id
    started = time.monotonic()
    seed_id = runner.start_run("seed", {}).run_id
    assert wait_final(initialized_db, seed_id).status == "succeeded"
    assert time.monotonic() - started < 5
    assert run_row(initialized_db, triage_id).status == "running"
    assert runner.wait_idle(120)
