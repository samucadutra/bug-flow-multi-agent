"""The report command with fake services."""

from __future__ import annotations

import subprocess
import sys
from contextlib import contextmanager

import pytest
from typer.testing import CliRunner

from bugflow.cli import app
from bugflow.cli.commands import report as report_module
from bugflow.cli.context import CliContext
from bugflow.logging_config import Redactor
from bugflow.services.errors import NotFoundError
from bugflow.services.reports import ReportFormat, ReportRead

runner = CliRunner()


class FakeEngine:
    disposed = False

    def dispose(self) -> None:
        self.disposed = True


class FakeSession:
    commits = 0

    def commit(self) -> None:
        FakeSession.commits += 1


@pytest.fixture
def context(monkeypatch, make_settings):
    FakeSession.commits = 0
    ctx = CliContext(make_settings(), FakeEngine(), Redactor())
    monkeypatch.setattr(report_module, "bootstrap", lambda: ctx)

    @contextmanager
    def factory_context():
        yield FakeSession()

    monkeypatch.setattr(report_module, "session_factory", lambda engine: factory_context)
    return ctx


def fake_get(monkeypatch, *, rendered: bool = False, error: Exception | None = None):
    calls = []

    def get_report(session, bug_id, format):
        calls.append((bug_id, format))
        if error:
            raise error
        text = "# Stored report\n" if format == ReportFormat.MD else "<p>Stored report</p>\n"
        return ReportRead(bug_id=bug_id, format=format, content=text, rendered=rendered)

    monkeypatch.setattr(report_module, "get_report", get_report)
    return calls


def test_help_lists_report(clean_env) -> None:
    assert "report" in runner.invoke(app, ["--help"]).output


def test_default_format_prints_the_stored_markdown(monkeypatch, context) -> None:
    calls = fake_get(monkeypatch)
    result = runner.invoke(app, ["report", "3"])
    assert result.exit_code == 0 and result.stdout == "# Stored report\n"
    assert calls == [(3, ReportFormat.MD)]
    assert context.engine.disposed and FakeSession.commits == 0


def test_html_format(monkeypatch, context) -> None:
    fake_get(monkeypatch)
    result = runner.invoke(app, ["report", "3", "--format", "html"])
    assert result.stdout == "<p>Stored report</p>\n"


def test_output_writes_the_file_and_confirms(monkeypatch, context, tmp_path) -> None:
    fake_get(monkeypatch)
    target = tmp_path / "report.html"
    result = runner.invoke(app, ["report", "3", "--format", "html", "--output", str(target)])
    assert result.exit_code == 0
    assert result.stdout == f"Report written to {target}\n"
    assert target.read_bytes() == b"<p>Stored report</p>\n"
    assert [path.name for path in tmp_path.iterdir()] == ["report.html"]


def test_invalid_format_is_a_usage_error(monkeypatch, context) -> None:
    fake_get(monkeypatch)
    result = runner.invoke(app, ["report", "3", "--format", "pdf"])
    assert result.exit_code == 2 and result.stdout == ""


@pytest.mark.parametrize("message", ["Bug 9 not found", "Bug 3 has no report; triage it first"])
def test_service_errors_go_to_stderr(monkeypatch, context, message) -> None:
    fake_get(monkeypatch, error=NotFoundError(message))
    result = runner.invoke(app, ["report", "3"])
    assert result.exit_code == 1 and message in result.stderr and result.stdout == ""


def test_write_failure_message_and_no_file(monkeypatch, context, tmp_path) -> None:
    fake_get(monkeypatch)
    target = tmp_path / "missing" / "report.md"
    result = runner.invoke(app, ["report", "3", "--output", str(target)])
    assert result.exit_code == 1
    assert result.stderr.startswith(f"Cannot write report to {target}")
    assert not (tmp_path / "missing").exists()


def test_commits_only_when_a_report_had_to_be_stored(monkeypatch, context) -> None:
    fake_get(monkeypatch, rendered=True)
    assert runner.invoke(app, ["report", "3"]).exit_code == 0
    assert FakeSession.commits == 1


def test_importing_the_command_does_not_import_crewai() -> None:
    code = (
        "import sys, bugflow.cli.commands.report;"
        "print('crewai' in sys.modules, 'litellm' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "False False"
