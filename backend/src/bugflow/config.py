"""Application settings. This is the only module that reads environment variables."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

MASK = "***"
_SCHEME_RE = re.compile(r"^postgresql(\+[A-Za-z0-9_]+)?$")
_URL_PASSWORD_RE = re.compile(r"(://[^/\s:@]*:)([^@\s]+)(@)")
_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class ConfigError(Exception):
    """Invalid or missing configuration. Carries a variable name, never a value."""

    def __init__(self, variable: str, message: str) -> None:
        super().__init__(message)
        self.variable = variable
        self.message = message


def mask_url_password(text: str) -> str:
    """Replace the password of any `scheme://user:password@host` text with `***`."""
    return _URL_PASSWORD_RE.sub(rf"\g<1>{MASK}\g<3>", text)


def url_password(url: str) -> str:
    """Return the password embedded in a connection URL, or an empty string."""
    try:
        return urlsplit(url).password or ""
    except ValueError:
        return ""


def _validate_database_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        raise ValueError("invalid") from None
    if not _SCHEME_RE.match(parts.scheme) or not host or not parts.path.strip("/"):
        raise ValueError("invalid")
    return value


class Settings(BaseSettings):
    """Typed settings loaded from the process environment and the root `.env` file."""

    model_config = SettingsConfigDict(
        extra="ignore",
        case_sensitive=False,
        env_file_encoding="utf-8",
    )

    database_url: str
    test_database_url: str | None = None
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 2
    similar_bugs_k: int = 5
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    log_level: LogLevel = "INFO"

    @field_validator("database_url")
    @classmethod
    def _check_database_url(cls, value: str) -> str:
        return _validate_database_url(value)

    @field_validator("test_database_url", mode="before")
    @classmethod
    def _check_test_database_url(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        if not isinstance(value, str):
            raise ValueError("invalid")
        return _validate_database_url(value)

    @field_validator("openai_model", "openai_embedding_model", "api_host")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("invalid")
        return value

    @field_validator("llm_timeout_seconds")
    @classmethod
    def _timeout_min(cls, value: int) -> int:
        if value < 1:
            raise ValueError("invalid")
        return value

    @field_validator("llm_max_retries")
    @classmethod
    def _retries_min(cls, value: int) -> int:
        if value < 0:
            raise ValueError("invalid")
        return value

    @field_validator("similar_bugs_k")
    @classmethod
    def _k_range(cls, value: int) -> int:
        if not 1 <= value <= 20:
            raise ValueError("invalid")
        return value

    @field_validator("api_port")
    @classmethod
    def _port_range(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("invalid")
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: Any) -> Any:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",")]
            if not items or any(not item for item in items):
                raise ValueError("invalid")
            return items
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _normalize_level(cls, value: Any) -> Any:
        if isinstance(value, str):
            upper = value.strip().upper()
            if upper in _LEVELS:
                return upper
        raise ValueError("invalid")

    @property
    def has_openai_key(self) -> bool:
        return bool(self.openai_api_key.get_secret_value())

    def require_openai_key(self) -> str:
        key = self.openai_api_key.get_secret_value()
        if not key:
            raise ConfigError("OPENAI_API_KEY", "OPENAI_API_KEY is not set")
        return key

    def secret_values(self) -> list[str]:
        """Secret values the log redactor must mask. Empty values are never returned."""
        values = [self.openai_api_key.get_secret_value()]
        for url in (self.database_url, self.test_database_url):
            if url:
                values.append(url_password(url))
        return [value for value in values if value]

    def __repr__(self) -> str:
        parts = []
        for name in type(self).model_fields:
            value = getattr(self, name)
            if name == "openai_api_key":
                shown = repr(MASK)
            elif name in ("database_url", "test_database_url") and value:
                shown = repr(mask_url_password(value))
            else:
                shown = repr(value)
            parts.append(f"{name}={shown}")
        return f"Settings({', '.join(parts)})"

    __str__ = __repr__


_UNSET: Any = object()


def load_settings(env_file: Path | None = _UNSET) -> Settings:
    """Build settings. The process environment wins over the file; `None` disables the file."""
    if env_file is _UNSET:
        env_file = DEFAULT_ENV_FILE
    failed: list[str] = []
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        for error in exc.errors(include_input=False, include_url=False):
            loc = error["loc"]
            failed.append(str(loc[0]).upper() if loc else "SETTINGS")
    variable = failed[0] if failed else "SETTINGS"
    if variable == "DATABASE_URL":
        raise ConfigError(variable, "DATABASE_URL is missing or invalid") from None
    raise ConfigError(variable, f"{variable} is invalid") from None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings for application code."""
    return load_settings()
