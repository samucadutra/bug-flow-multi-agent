"""`bugflow triage` as a child process against the stand-in and the compose database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from mocks.fake_openai_server import INVALID_KEY, VALID_KEY, default_reply
from tests_helpers import RESULT_TABLES, add_bug, result_row_counts, stored_status

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
BINARY = Path(sys.executable).parent / "bugflow"
ROOT_ENV_FILE = BACKEND.parent / ".env"


@pytest.fixture
def cli(test_engine, stand_in):
    url = test_engine.url.render_as_string(hide_password=False)
    assert not ROOT_ENV_FILE.exists(), "the contracts require that no root .env file exists"

    def run(*args, key=VALID_KEY):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "LOG_LEVEL", "SIMILAR"))
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
            timeout=180,
        )

    return run


def rows(engine, query):
    with engine.connect() as connection:
        return connection.execute(text(query)).all()


def wrong_severity(stand_in, contains=None):
    reply = default_reply("Severity Classifier")
    reply["severity"] = "high"
    entry = {"role": "Severity Classifier", "json": reply, "repeat": 2}
    if contains:
        entry["contains"] = contains
    stand_in.script_chat([entry])


def test_help_lists_triage(cli):
    result = cli("--help")
    assert result.returncode == 0
    line = next(
        line for line in result.stdout.splitlines() if line.lstrip("│ ").startswith("triage")
    )
    assert "Run the triage agents" in line


def test_triage_one_bug(cli, open_bug, initialized_db):
    result = cli("triage", "--bug", str(open_bug))
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "AG1 Component Classifier: backend"
    assert lines[1] == "AG2 Severity Classifier: major"
    assert lines[2] == "AG3 Technical Analyst: 2 debugging steps, 0 similar bugs referenced"
    assert lines[3] == "AG4 Resolution Manager: backend / high / planned"
    assert lines[4] == "AG5 Bug Documenter: 1 key takeaways, 1 next steps"
    assert lines[-1] == f"Bug {open_bug} processed" and len(lines) == 6
    assert stored_status(initialized_db, open_bug) == "processed"
    assert result_row_counts(initialized_db, open_bug) == dict.fromkeys(RESULT_TABLES, 1)
    assert (
        rows(initialized_db, "SELECT status FROM run_steps ORDER BY position")
        == [("succeeded",)] * 5
    )
    run = rows(initialized_db, "SELECT type, status, progress_done, progress_total FROM runs")
    assert run == [("triage", "succeeded", 5, 5)]
    assert "crewai" not in result.stdout.lower() and result.stderr == ""


def test_invalid_output_fails_the_bug(cli, open_bug, initialized_db, stand_in):
    wrong_severity(stand_in)
    result = cli("triage", "--bug", str(open_bug))
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1] == (
        f"Bug {open_bug} failed: AG2 returned invalid severity 'high'"
    )
    assert stored_status(initialized_db, open_bug) == "failed"
    assert result_row_counts(initialized_db, open_bug) == dict.fromkeys(RESULT_TABLES, 0)
    assert rows(initialized_db, "SELECT status FROM run_steps ORDER BY position") == [
        ("succeeded",),
        ("failed",),
        ("skipped",),
        ("skipped",),
        ("skipped",),
    ]


def test_processing_bug_is_rejected(cli, initialized_db, stand_in):
    bug_id = add_bug(initialized_db, status="processing")
    result = cli("triage", "--bug", str(bug_id))
    assert result.returncode != 0
    assert f"Bug {bug_id} is already being processed" in result.stderr
    assert stored_status(initialized_db, bug_id) == "processing"
    assert rows(initialized_db, "SELECT count(*) FROM runs") == [(0,)]
    assert stand_in.chat_requests() == []


def test_processed_and_unknown_bugs_are_rejected(cli, initialized_db):
    bug_id = add_bug(initialized_db, status="processed")
    result = cli("triage", "--bug", str(bug_id))
    assert result.returncode == 1
    assert f"Bug {bug_id} has already been processed; reopen it first" in result.stderr
    missing = cli("triage", "--bug", "999999")
    assert missing.returncode == 1 and "Bug 999999 not found" in missing.stderr


@pytest.fixture
def three_open(initialized_db):
    return [add_bug(initialized_db, title=title) for title in ("Bug one", "Bug two", "Bug three")]


def test_triage_all(cli, three_open, initialized_db):
    result = cli("triage", "--all")
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    for bug_id in three_open:
        assert f"Bug {bug_id} processed" in lines
    assert lines[-1] == "Triaged 3 bugs: 3 processed, 0 failed"
    assert rows(initialized_db, "SELECT status FROM bugs") == [("processed",)] * 3


def test_one_failure_does_not_stop_triage_all(cli, three_open, initialized_db, stand_in):
    wrong_severity(stand_in, contains="Bug two")
    result = cli("triage", "--all")
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1] == "Triaged 3 bugs: 2 processed, 1 failed"
    assert rows(initialized_db, "SELECT title, status FROM bugs ORDER BY id") == [
        ("Bug one", "processed"),
        ("Bug two", "failed"),
        ("Bug three", "processed"),
    ]


def test_triage_all_without_open_bugs(cli, initialized_db, stand_in):
    add_bug(initialized_db, status="processed")
    result = cli("triage", "--all")
    assert result.returncode == 0 and result.stdout == "No open bugs to triage\n"
    assert stand_in.chat_requests() == []


@pytest.mark.parametrize("args", [[], ["--bug", "1", "--all"]])
def test_an_option_is_required(cli, open_bug, initialized_db, args):
    result = cli("triage", *args)
    assert result.returncode == 2
    assert "Specify exactly one of --bug or --all" in result.stderr
    assert rows(initialized_db, "SELECT count(*) FROM runs") == [(0,)]


def test_missing_api_key(cli, open_bug, initialized_db, stand_in):
    result = cli("triage", "--bug", str(open_bug), key=None)
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1] == (
        f"Bug {open_bug} failed: AG1 failed: OPENAI_API_KEY is not set"
    )
    assert stored_status(initialized_db, open_bug) == "failed"
    assert stand_in.chat_requests() == []


def test_invalid_api_key_leaves_no_key_in_any_output(cli, open_bug, initialized_db):
    result = cli("triage", "--bug", str(open_bug), key=INVALID_KEY)
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1] == (
        f"Bug {open_bug} failed: AG1 failed: OpenAI authentication failed"
    )
    assert INVALID_KEY not in result.stdout + result.stderr
    dump = str(rows(initialized_db, "SELECT * FROM run_steps")) + str(
        rows(initialized_db, "SELECT * FROM run_logs")
    )
    assert INVALID_KEY not in dump


def test_database_unreachable(cli, open_bug, test_engine, stand_in):
    import os as _os

    env_url = "postgresql+psycopg://bugflow:bugflow@127.0.0.1:9/bugflow"
    result = subprocess.run(
        [str(BINARY), "triage", "--bug", "1"],
        cwd=BACKEND,
        env={**_os.environ, "DATABASE_URL": env_url, "OPENAI_API_KEY": VALID_KEY},
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    assert result.returncode == 1
    assert "Cannot connect to the database" in result.stderr
    assert "bugflow:bugflow" not in result.stdout + result.stderr
