import sys

import pytest
from typer.testing import CliRunner

from bugflow.cli import app
from bugflow.cli.commands import reopen as reopen_module
from bugflow.cli.context import CliContext
from bugflow.logging_config import Redactor
from bugflow.services.errors import NotFoundError, StateConflictError

runner = CliRunner()
PROMPT = "This deletes the results and report of bug 3. Type 'yes' to continue:"


class FakeEngine:
    disposed = False

    def dispose(self):
        self.disposed = True


@pytest.fixture
def context(monkeypatch, make_settings):
    ctx = CliContext(make_settings(), FakeEngine(), Redactor())
    monkeypatch.setattr(reopen_module, "bootstrap", lambda: ctx)
    return ctx


@pytest.fixture
def calls(monkeypatch, context):
    recorded = []
    monkeypatch.setattr(reopen_module, "reopen_bug", lambda engine, bug_id: recorded.append(bug_id))
    return recorded


def test_help_lists_reopen(clean_env):
    assert "reopen" in runner.invoke(app, ["--help"]).output


def test_yes_flag_skips_prompt(calls, context):
    result = runner.invoke(app, ["reopen", "3", "--yes"])
    assert result.exit_code == 0
    assert result.stdout == "Bug 3 reopened\n"
    assert calls == [3] and context.engine.disposed


@pytest.mark.parametrize("answer", ["yes\n", "YES\n", "Yes\n"])
def test_typed_yes_confirms(calls, answer):
    result = runner.invoke(app, ["reopen", "3"], input=answer)
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [PROMPT + " ", "Bug 3 reopened"]
    assert calls == [3]


@pytest.mark.parametrize("answer", ["no\n", "\n", ""])
def test_other_answers_abort(calls, answer):
    result = runner.invoke(app, ["reopen", "3"], input=answer)
    assert result.exit_code == 1
    assert "Aborted: nothing was deleted" in result.stdout
    assert calls == []


@pytest.mark.parametrize(
    "error",
    [
        StateConflictError("Bug 3 is already open"),
        NotFoundError("Bug 3 not found"),
    ],
)
def test_service_errors_go_to_stderr(monkeypatch, context, error):
    def fail(engine, bug_id):
        raise error

    monkeypatch.setattr(reopen_module, "reopen_bug", fail)
    result = runner.invoke(app, ["reopen", "3", "--yes"])
    assert result.exit_code == 1
    assert error.message in result.stderr and result.stdout == ""
    assert context.engine.disposed


def test_missing_id_is_a_usage_error(clean_env):
    assert runner.invoke(app, ["reopen"]).exit_code == 2


def test_module_does_not_import_llm_libraries():
    import subprocess

    code = (
        "import sys, bugflow.cli.commands.reopen;"
        "print('crewai' in sys.modules, 'litellm' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.stdout.split() == ["False", "False"], out.stderr
