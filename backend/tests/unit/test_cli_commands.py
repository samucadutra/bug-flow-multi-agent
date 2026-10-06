import pytest
from typer.testing import CliRunner

from bugflow.cli import app
from bugflow.cli.commands import check as check_module
from bugflow.cli.commands import db as db_module
from bugflow.cli.context import CliContext
from bugflow.config import ConfigError
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.logging_config import Redactor
from bugflow.services.db_admin import InitResult, SeedResult
from bugflow.services.errors import ServiceError
from bugflow.services.health import CheckResult, HealthReport

runner = CliRunner()


class FakeEngine:
    disposed = False

    def dispose(self):
        self.disposed = True


@pytest.fixture
def context(monkeypatch, make_settings):
    ctx = CliContext(make_settings(), FakeEngine(), Redactor())
    for module in (check_module, db_module):
        monkeypatch.setattr(module, "bootstrap", lambda: ctx)
    return ctx


def report(db=True, vector=True, llm=True):
    def result(ok, message):
        return CheckResult(ok=ok, message=message)

    return HealthReport(
        database=result(db, "Cannot connect to the database"),
        vector_search=result(vector, "pgvector extension is not available"),
        llm=result(llm, "OPENAI_API_KEY is not set"),
    )


def test_help_lists_commands_in_english(clean_env):
    top = runner.invoke(app, ["--help"])
    assert top.exit_code == 0 and "check" in top.output and "db" in top.output
    sub = runner.invoke(app, ["db", "--help"])
    for word in ("init", "seed", "reset", "Apply database migrations"):
        assert word in sub.output


def test_version_loads_no_settings(clean_env, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("settings must not load")

    monkeypatch.setattr("bugflow.cli.context.load_settings", boom)
    assert runner.invoke(app, ["--version"]).exit_code == 0


def test_check_prints_three_lines(monkeypatch, context):
    monkeypatch.setattr(check_module, "check_health", lambda settings, engine: report(llm=False))
    result = runner.invoke(app, ["check"])
    assert result.stdout.splitlines() == [
        "database: ok",
        "vector search: ok",
        "llm: failed: OPENAI_API_KEY is not set",
    ]
    assert result.exit_code == 1 and context.engine.disposed
    monkeypatch.setattr(check_module, "check_health", lambda settings, engine: report())
    assert runner.invoke(app, ["check"]).exit_code == 0


def test_init_prints_migrations(monkeypatch, context):
    monkeypatch.setattr(
        db_module,
        "run_init",
        lambda engine, redactor: InitResult(
            applied_revisions=["0001", "0002"], current_revision="0002"
        ),
    )
    assert runner.invoke(app, ["db", "init"]).stdout.splitlines() == [
        "Applied migration 0001",
        "Applied migration 0002",
    ]
    monkeypatch.setattr(
        db_module,
        "run_init",
        lambda engine, redactor: InitResult(applied_revisions=[], current_revision="0001"),
    )
    assert runner.invoke(app, ["db", "init"]).stdout == "Database schema is already up to date\n"


@pytest.mark.parametrize(
    ("created", "present", "message"),
    [
        (20, 0, "Seeded 20 bugs"),
        (0, 20, "20 bugs already present, nothing to do"),
        (5, 15, "Seeded 5 bugs (15 already present)"),
    ],
)
def test_seed_messages(monkeypatch, context, created, present, message):
    monkeypatch.setattr(
        db_module,
        "run_seed",
        lambda engine, redactor: SeedResult(created=created, already_present=present),
    )
    assert runner.invoke(app, ["db", "seed"]).stdout == f"{message}\n"


@pytest.fixture
def reset_calls(monkeypatch, context):
    calls = []
    monkeypatch.setattr(
        db_module,
        "run_reset",
        lambda engine, redactor: (
            calls.append(1) or InitResult(applied_revisions=[], current_revision="")
        ),
    )
    return calls


def test_reset_yes_flag_skips_prompt(reset_calls):
    result = runner.invoke(app, ["db", "reset", "--yes"])
    assert result.exit_code == 0 and len(reset_calls) == 1
    assert result.stdout == "Database reset: schema recreated, no data loaded\n"


@pytest.mark.parametrize(
    ("answer", "confirmed"),
    [
        ("yes\n", True),
        (" YES \n", True),
        ("no\n", False),
        ("\n", False),
        ("", False),
        ("y\n", False),
    ],
)
def test_reset_requires_typed_yes(reset_calls, answer, confirmed):
    result = runner.invoke(app, ["db", "reset"], input=answer)
    assert "This deletes all data. Type 'yes' to continue:" in result.stdout
    if confirmed:
        assert result.exit_code == 0 and len(reset_calls) == 1
    else:
        assert result.exit_code == 1 and reset_calls == []
        assert "Aborted: nothing was deleted" in result.stdout


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (
            ConfigError("DATABASE_URL", "DATABASE_URL is missing or invalid"),
            "DATABASE_URL is missing or invalid",
        ),
        (DatabaseUnavailableError(), "Cannot connect to the database"),
        (ServiceError("Bug 1 not found"), "Bug 1 not found"),
        (RuntimeError("weird sk-test-canary-1234567890abcdef"), "Unexpected error: weird ***"),
    ],
)
def test_errors_map_to_exit_one(monkeypatch, context, error, message):
    def explode(engine, redactor):
        raise error

    monkeypatch.setattr(db_module, "run_init", explode)
    result = runner.invoke(app, ["db", "init"])
    assert result.exit_code == 1
    assert result.stderr.strip() == message and result.stdout == ""
    assert "Traceback" not in result.stderr
