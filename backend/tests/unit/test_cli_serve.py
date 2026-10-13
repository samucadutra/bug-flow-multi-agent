"""`bugflow serve`: defaults, options, the loopback warning and configuration errors."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from bugflow.cli import app
from bugflow.cli.commands.serve import is_loopback

runner = CliRunner()
URL = "postgresql+psycopg://bugflow:pw@127.0.0.1:1/bugflow"


@pytest.fixture
def uvicorn_calls(clean_env, monkeypatch):
    import uvicorn

    clean_env.setenv("DATABASE_URL", URL)
    calls: list[dict] = []
    monkeypatch.setattr(uvicorn, "run", lambda application, **kwargs: calls.append(kwargs))
    return calls


def test_serve_defaults_bind_loopback(uvicorn_calls):
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0
    assert uvicorn_calls[0]["host"] == "127.0.0.1"
    assert uvicorn_calls[0]["port"] == 8000
    assert "Serving BugFlow API on http://127.0.0.1:8000 (docs at /docs)" in result.output
    assert "no authentication" not in result.output


def test_options_override_settings(uvicorn_calls):
    result = runner.invoke(app, ["serve", "--host", "127.0.0.2", "--port", "9001"])
    assert result.exit_code == 0
    assert (uvicorn_calls[0]["host"], uvicorn_calls[0]["port"]) == ("127.0.0.2", 9001)
    assert "http://127.0.0.2:9001" in result.output


def test_environment_sets_port(uvicorn_calls, clean_env):
    clean_env.setenv("API_PORT", "8123")
    result = runner.invoke(app, ["serve"])
    assert uvicorn_calls[0]["port"] == 8123
    assert "http://127.0.0.1:8123" in result.output


def test_non_loopback_host_warns(uvicorn_calls):
    result = runner.invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 0
    assert "no authentication" in result.output


def test_missing_database_url_fails_fast(clean_env, monkeypatch):
    import uvicorn

    started: list[int] = []
    monkeypatch.setattr(uvicorn, "run", lambda *a, **k: started.append(1))
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 1
    assert "DATABASE_URL is missing or invalid" in result.output
    assert started == []


def test_serve_is_listed_in_help(clean_env):
    result = runner.invoke(app, ["--help"])
    assert "serve" in result.output
    assert "Start the BugFlow API server." in result.output


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("localhost", True),
        ("::1", True),
        ("0.0.0.0", False),
        ("10.0.0.5", False),
        ("example.com", False),
    ],
)
def test_is_loopback(host, expected):
    assert is_loopback(host) is expected
