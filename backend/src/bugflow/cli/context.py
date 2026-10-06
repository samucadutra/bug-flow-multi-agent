"""CLI bootstrap: settings, logging and the engine are built only when a command runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bugflow.cli.output import register_secrets
from bugflow.config import Settings, load_settings
from bugflow.db.engine import create_db_engine
from bugflow.logging_config import Redactor, configure_logging


@dataclass
class CliContext:
    settings: Settings
    engine: Any
    redactor: Redactor

    def close(self) -> None:
        self.engine.dispose()


def bootstrap() -> CliContext:
    """Load settings, configure logging and build the engine (no connection is opened)."""
    settings = load_settings()
    secrets = settings.secret_values()
    register_secrets(secrets)
    configure_logging(settings)
    return CliContext(
        settings=settings,
        engine=create_db_engine(settings.database_url),
        redactor=Redactor(secrets),
    )
