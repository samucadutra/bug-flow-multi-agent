"""Health check: database, vector search and LLM, evaluated independently."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine, text

from bugflow.config import Settings

DB_UNREACHABLE = "Cannot connect to the database"
VECTOR_NOT_CHECKED = "Database unreachable; vector search not checked"
VECTOR_MISSING = "pgvector extension is not available; use the pgvector/pgvector image"
KEY_MISSING = "OPENAI_API_KEY is not set"
LLM_AUTH = "OpenAI authentication failed"
LLM_CONNECTION = "Cannot reach the OpenAI API"
LLM_TIMEOUT = "OpenAI request timed out"
LLM_FAILED = "OpenAI request failed"


class CheckResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ok: bool
    message: str = "ok"

    def line(self, label: str) -> str:
        return f"{label}: ok" if self.ok else f"{label}: failed: {self.message}"


class HealthReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    database: CheckResult
    vector_search: CheckResult
    llm: CheckResult

    @property
    def all_ok(self) -> bool:
        return self.database.ok and self.vector_search.ok and self.llm.ok

    @property
    def summary(self) -> str:
        return "All checks passed" if self.all_ok else "Some checks failed"

    def lines(self) -> list[str]:
        return [
            self.database.line("database"),
            self.vector_search.line("vector search"),
            self.llm.line("llm"),
        ]


class LlmProbeError(Exception):
    """A probe failure with a fixed, secret-free message."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class LlmProbe(Protocol):
    def check(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        """Return when the model is reachable; raise `LlmProbeError` otherwise."""


class OpenAILlmProbe:
    """Looks up the configured chat model through the OpenAI SDK (no tokens are spent)."""

    def __init__(self, client_factory: object | None = None) -> None:
        self._client_factory = client_factory

    def _factory(self) -> object:
        if self._client_factory is not None:
            return self._client_factory
        import openai

        return openai.OpenAI

    def check(self, *, api_key: str, model: str, timeout_seconds: float) -> None:
        import openai

        try:
            client = self._factory()(api_key=api_key, timeout=timeout_seconds, max_retries=0)
            client.models.retrieve(model)
        except openai.AuthenticationError:
            raise LlmProbeError(LLM_AUTH) from None
        except openai.APITimeoutError:
            raise LlmProbeError(LLM_TIMEOUT) from None
        except openai.APIConnectionError:
            raise LlmProbeError(LLM_CONNECTION) from None
        except Exception:
            raise LlmProbeError(LLM_FAILED) from None


def _check_database(engine: Engine) -> tuple[CheckResult, CheckResult]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            database = CheckResult(ok=True)
            try:
                has_vector = (
                    connection.execute(
                        text("SELECT 1 FROM pg_available_extensions WHERE name = :name"),
                        {"name": "vector"},
                    ).first()
                    is not None
                )
            except Exception:
                has_vector = False
    except Exception:
        return (
            CheckResult(ok=False, message=DB_UNREACHABLE),
            CheckResult(ok=False, message=VECTOR_NOT_CHECKED),
        )
    vector = CheckResult(ok=True) if has_vector else CheckResult(ok=False, message=VECTOR_MISSING)
    return database, vector


def _check_llm(settings: Settings, llm_probe: LlmProbe | None) -> CheckResult:
    if not settings.has_openai_key:
        return CheckResult(ok=False, message=KEY_MISSING)
    probe = llm_probe or OpenAILlmProbe()
    try:
        probe.check(
            api_key=settings.openai_api_key.get_secret_value(),
            model=settings.openai_model,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    except LlmProbeError as exc:
        return CheckResult(ok=False, message=exc.message)
    except Exception:
        return CheckResult(ok=False, message=LLM_FAILED)
    return CheckResult(ok=True)


def check_health(
    settings: Settings, engine: Engine, llm_probe: LlmProbe | None = None
) -> HealthReport:
    """Evaluate the three checks; one failing never prevents the others."""
    database, vector = _check_database(engine)
    return HealthReport(
        database=database, vector_search=vector, llm=_check_llm(settings, llm_probe)
    )
