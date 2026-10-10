"""The report command and `triage` as child processes against the compose database."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from mocks.fake_openai_server import VALID_KEY
from report_helpers import stored_texts

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[3]
BINARY = Path(sys.executable).parent / "bugflow"
ROOT_ENV_FILE = BACKEND.parent / ".env"


@pytest.fixture
def cli(test_engine, stand_in):
    url = test_engine.url.render_as_string(hide_password=False)
    assert not ROOT_ENV_FILE.exists(), "the contracts require that no root .env file exists"

    def run(*args, with_llm=False):
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "LOG_LEVEL", "SIMILAR"))
        }
        env.update(DATABASE_URL=url, TZ="UTC")
        if with_llm:
            env.update(OPENAI_API_KEY=VALID_KEY, OPENAI_BASE_URL=stand_in.base_url)
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


def test_help_lists_report(cli) -> None:
    result = cli("--help")
    assert result.returncode == 0
    line = next(
        line for line in result.stdout.splitlines() if line.lstrip("│ ").startswith("report")
    )
    assert "report" in line and len(line.split()) > 2


def test_prints_the_stored_markdown_and_html(cli, stored_report_bug) -> None:
    md = cli("report", str(stored_report_bug))
    assert (md.returncode, md.stdout) == (0, "# Stored report\n")
    html = cli("report", str(stored_report_bug), "--format", "html")
    assert (html.returncode, html.stdout) == (0, "<p>Stored report</p>\n")


def test_output_file(cli, stored_report_bug, tmp_path) -> None:
    target = tmp_path / "report.html"
    result = cli("report", str(stored_report_bug), "--format", "html", "--output", str(target))
    assert result.returncode == 0
    assert result.stdout == f"Report written to {target}\n"
    assert target.read_bytes() == b"<p>Stored report</p>\n"


def test_a_missing_stored_report_is_rendered_and_committed(cli, report_bug, initialized_db) -> None:
    bug_id = report_bug[0]
    result = cli("report", str(bug_id))
    assert result.returncode == 0, result.stderr
    assert result.stdout.split("\n")[0] == "# Checkout button does nothing on Safari 17"
    assert "Clicking Place order shows no response and no network call." in result.stdout
    assert "Add an item, go to checkout in Safari 17, click the button." in result.stdout
    markdown, html = stored_texts(initialized_db, bug_id)
    assert markdown == result.stdout and html


def test_unprocessed_bug_has_no_report(cli, unprocessed_bug) -> None:
    result = cli("report", str(unprocessed_bug))
    assert result.returncode == 1 and result.stdout == ""
    assert f"Bug {unprocessed_bug} has no report; triage it first" in result.stderr


def test_unknown_bug(cli, initialized_db) -> None:
    result = cli("report", "999999")
    assert result.returncode == 1 and "Bug 999999 not found" in result.stderr


def test_invalid_format(cli, stored_report_bug) -> None:
    result = cli("report", str(stored_report_bug), "--format", "pdf")
    assert result.returncode == 2 and result.stdout == ""


def test_unwritable_output_path(cli, stored_report_bug, tmp_path) -> None:
    target = tmp_path / "missing" / "report.md"
    result = cli("report", str(stored_report_bug), "--output", str(target))
    assert result.returncode == 1
    assert result.stderr.startswith(f"Cannot write report to {target}")
    assert not (tmp_path / "missing").exists()


def test_triage_through_the_cli_stores_the_report(cli, open_bug, initialized_db) -> None:
    result = cli("triage", "--bug", str(open_bug), with_llm=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[-1] == f"Bug {open_bug} processed"
    markdown, html = stored_texts(initialized_db, open_bug)
    assert markdown and html
    assert markdown.split("\n")[0] == "# Checkout button does nothing on Safari 17"
    shown = cli("report", str(open_bug))
    assert shown.stdout == markdown
