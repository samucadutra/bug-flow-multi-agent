"""`bugflow reopen` as a child process against the test database."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests_helpers import RESULT_TABLES, kept_snapshot, result_row_counts, stored_status

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
BINARY = Path(sys.executable).parent / "bugflow"
ROOT_ENV_FILE = BACKEND.parent / ".env"


@pytest.fixture
def cli(test_engine):
    url = test_engine.url.render_as_string(hide_password=False)
    assert not ROOT_ENV_FILE.exists(), "the contracts require that no root .env file exists"

    def run(*args, stdin=None):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "LOG_LEVEL", "SIMILAR"))
        }
        env.update(DATABASE_URL=url, TZ="UTC")
        return subprocess.run(
            [str(BINARY), *args],
            cwd=BACKEND,
            env=env,
            input=stdin if stdin is not None else "",
            capture_output=True,
            text=True,
            timeout=120,
        )

    return run


def test_help_lists_reopen(cli):
    result = cli("--help")
    assert result.returncode == 0
    line = next(x for x in result.stdout.splitlines() if x.lstrip("│ ").startswith("reopen"))
    assert "Return a processed or failed bug to open" in line


def test_reopen_confirmed_by_typing(cli, triaged_bug, initialized_db):
    result = cli("reopen", str(triaged_bug), stdin="yes\n")
    assert result.returncode == 0, result.stderr
    prompt = f"This deletes the results and report of bug {triaged_bug}. Type 'yes' to continue:"
    assert prompt in result.stdout
    assert result.stdout.splitlines()[-1] == f"Bug {triaged_bug} reopened"
    assert stored_status(initialized_db, triaged_bug) == "open"
    assert result_row_counts(initialized_db, triaged_bug) == dict.fromkeys(RESULT_TABLES, 0)


def test_reopen_with_yes_flag(cli, triaged_bug, initialized_db):
    kept = kept_snapshot(initialized_db)
    result = cli("reopen", str(triaged_bug), "--yes")
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"Bug {triaged_bug} reopened\n"
    assert stored_status(initialized_db, triaged_bug) == "open"
    assert result_row_counts(initialized_db, triaged_bug) == dict.fromkeys(RESULT_TABLES, 0)
    assert kept_snapshot(initialized_db) == kept


@pytest.mark.parametrize("answer", ["no\n", ""])
def test_reopen_declined_or_without_answer(cli, triaged_bug, initialized_db, answer):
    result = cli("reopen", str(triaged_bug), stdin=answer)
    assert result.returncode == 1
    assert "Aborted: nothing was deleted" in result.stdout
    assert stored_status(initialized_db, triaged_bug) == "processed"
    assert result_row_counts(initialized_db, triaged_bug) == dict.fromkeys(RESULT_TABLES, 1)


def test_reopen_failed_bug(cli, failed_triaged_bug, initialized_db):
    result = cli("reopen", str(failed_triaged_bug), "--yes")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == f"Bug {failed_triaged_bug} reopened"
    assert stored_status(initialized_db, failed_triaged_bug) == "open"
    assert len(kept_snapshot(initialized_db)["run_steps"]) == 5


def test_processing_bug_is_rejected(cli, busy_bug, initialized_db):
    kept = kept_snapshot(initialized_db)
    result = cli("reopen", str(busy_bug), "--yes")
    assert result.returncode == 1
    assert f"Bug {busy_bug} is being processed and cannot be reopened" in result.stderr
    assert stored_status(initialized_db, busy_bug) == "processing"
    assert kept_snapshot(initialized_db) == kept


def test_open_bug_is_rejected(cli, untriaged_bug, initialized_db):
    result = cli("reopen", str(untriaged_bug), "--yes")
    assert result.returncode == 1
    assert f"Bug {untriaged_bug} is already open" in result.stderr
    assert stored_status(initialized_db, untriaged_bug) == "open"


def test_unknown_bug(cli, initialized_db):
    result = cli("reopen", "999999", "--yes")
    assert result.returncode == 1
    assert "Bug 999999 not found" in result.stderr


def test_id_is_required(cli, triaged_bug, initialized_db):
    result = cli("reopen")
    assert result.returncode == 2
    assert "Usage" in result.stderr
    assert stored_status(initialized_db, triaged_bug) == "processed"
