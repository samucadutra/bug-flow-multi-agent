"""Shared fixtures. Tests never read the developer's real environment or `.env`."""

from __future__ import annotations

import os
from collections.abc import Callable

import pytest

CANARY_API_KEY = "sk-test-canary-1234567890abcdef"
CANARY_DB_PASSWORD = "s3cretpw"
CANARY_DB_URL = f"postgresql+psycopg://bugflow:{CANARY_DB_PASSWORD}@localhost:5432/bugflow"

BACKEND_VARIABLES = (
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "SIMILAR_BUGS_K",
    "API_HOST",
    "API_PORT",
    "CORS_ORIGINS",
    "LOG_LEVEL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "NEXT_PUBLIC_API_BASE_URL",
)


@pytest.fixture
def canary_api_key() -> str:
    return CANARY_API_KEY


@pytest.fixture
def canary_db_url() -> str:
    return CANARY_DB_URL


@pytest.fixture
def canary_db_password() -> str:
    return CANARY_DB_PASSWORD


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Remove every BugFlow variable from the process environment."""
    for name in BACKEND_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def make_settings(clean_env: pytest.MonkeyPatch) -> Callable[..., object]:
    """Build settings from explicit variables with the env file disabled."""
    from bugflow.config import load_settings

    def _make(**env: str):
        base = {"DATABASE_URL": CANARY_DB_URL}
        base.update(env)
        for key, value in base.items():
            clean_env.setenv(key, value)
        return load_settings(env_file=None)

    return _make


@pytest.fixture(autouse=True)
def _utc_timezone(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TZ", "UTC")
    assert os.environ["TZ"] == "UTC"
