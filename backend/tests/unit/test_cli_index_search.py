import pytest
from typer.testing import CliRunner

from bugflow.cli import app
from bugflow.cli.commands import index as index_module
from bugflow.cli.commands import search as search_module
from bugflow.cli.context import CliContext
from bugflow.config import ConfigError
from bugflow.logging_config import Redactor
from bugflow.services.embeddings import IndexResult
from bugflow.services.errors import SchemaNotInitializedError
from bugflow.services.llm_client import LlmError
from bugflow.services.similarity import NOT_INDEXED_HINT, SearchResult, SimilarBug

runner = CliRunner()


class FakeEngine:
    disposed = False

    def dispose(self):
        self.disposed = True


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def context(monkeypatch, make_settings):
    ctx = CliContext(make_settings(), FakeEngine(), Redactor())
    for module in (index_module, search_module):
        monkeypatch.setattr(module, "bootstrap", lambda: ctx)
    monkeypatch.setattr(search_module, "session_factory", lambda engine: FakeSession)
    return ctx


def items(count):
    return [
        SimilarBug(bug_id=i, title=f"Bug {i}", status="open", score=1 - i / 100)
        for i in range(1, count + 1)
    ]


def test_help_lists_both_commands(clean_env):
    out = runner.invoke(app, ["--help"]).output
    assert "index" in out and "search" in out


def test_index_prints_summary(monkeypatch, context):
    monkeypatch.setattr(index_module, "run_index", lambda *a: IndexResult(20, 20))
    result = runner.invoke(app, ["index"])
    assert result.stdout == "Indexed 20/20 bugs\n" and result.exit_code == 0
    assert context.engine.disposed


@pytest.mark.parametrize(
    "error",
    [
        ConfigError("OPENAI_API_KEY", "OPENAI_API_KEY is not set"),
        LlmError("OpenAI authentication failed"),
        SchemaNotInitializedError(),
    ],
)
def test_index_maps_errors_to_exit_one(monkeypatch, context, error):
    def boom(*args):
        raise error

    monkeypatch.setattr(index_module, "run_index", boom)
    result = runner.invoke(app, ["index"])
    assert result.exit_code == 1 and result.stderr == f"{error}\n" and result.stdout == ""


def test_search_default_limit_and_row_format(monkeypatch, context):
    seen = {}

    def fake(session, get_client, text, limit):
        seen.update(text=text, limit=limit)
        return SearchResult(items=items(2))

    monkeypatch.setattr(search_module, "search_similar", fake)
    result = runner.invoke(app, ["search", "button does nothing"])
    assert seen == {"text": "button does nothing", "limit": 5}
    assert result.stdout.splitlines() == [
        "SCORE  ID  TITLE  STATUS",
        "0.99  1  Bug 1  open",
        "0.98  2  Bug 2  open",
    ]


def test_search_limit_option(monkeypatch, context):
    seen = {}
    monkeypatch.setattr(
        search_module,
        "search_similar",
        lambda session, get_client, text, limit: seen.update(limit=limit) or SearchResult(items=[]),
    )
    assert runner.invoke(app, ["search", "x", "--limit", "20"]).exit_code == 0
    assert seen["limit"] == 20


def test_search_rejects_limit_21_with_field_message(context):
    result = runner.invoke(app, ["search", "x", "--limit", "21"])
    assert result.exit_code == 1
    assert "Validation failed: limit: must be between 1 and 20" in result.stderr


def test_search_rejects_empty_text(context):
    result = runner.invoke(app, ["search", ""])
    assert result.exit_code == 1 and "Search text must not be empty" in result.stderr


def test_search_prints_the_hint(monkeypatch, context):
    monkeypatch.setattr(
        search_module,
        "search_similar",
        lambda *a: SearchResult(items=[], hint=NOT_INDEXED_HINT),
    )
    result = runner.invoke(app, ["search", "x"])
    assert result.exit_code == 0 and result.stdout == "No bugs are indexed; run index\n"


def test_search_provider_error(monkeypatch, context):
    def boom(*args):
        raise LlmError("OpenAI authentication failed")

    monkeypatch.setattr(search_module, "search_similar", boom)
    result = runner.invoke(app, ["search", "x"])
    assert result.exit_code == 1 and result.stderr == "OpenAI authentication failed\n"


def test_context_client_is_lazy_and_requires_a_key(context):
    with pytest.raises(ConfigError, match="^OPENAI_API_KEY is not set$"):
        context.get_client()
