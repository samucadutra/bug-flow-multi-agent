"""CLI bootstrap: settings, logging and the engine are built only when a command runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bugflow.cli.output import register_secrets
from bugflow.config import Settings, load_settings
from bugflow.db.engine import create_db_engine
from bugflow.logging_config import Redactor, configure_logging
from bugflow.services.llm_client import OpenAILlmClient
from bugflow.services.reports import install_report_hook


@dataclass
class CliContext:
    settings: Settings
    engine: Any
    redactor: Redactor
    _client: OpenAILlmClient | None = field(default=None, init=False, repr=False)

    def get_client(self) -> OpenAILlmClient:
        """Build the LLM client on first use; raises `ConfigError` when the key is not set."""
        if self._client is None:
            self._client = OpenAILlmClient.from_settings(self.settings)
        return self._client

    def close(self) -> None:
        self.engine.dispose()


def bootstrap() -> CliContext:
    """Load settings, configure logging and build the engine (no connection is opened)."""
    settings = load_settings()
    secrets = settings.secret_values()
    register_secrets(secrets)
    configure_logging(settings)
    install_report_hook()
    return CliContext(
        settings=settings,
        engine=create_db_engine(settings.database_url),
        redactor=Redactor(secrets),
    )
