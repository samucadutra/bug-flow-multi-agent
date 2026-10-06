"""Output helpers: printing, typed confirmation and error-to-exit-code mapping."""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from typing import Any

import typer

from bugflow.config import ConfigError
from bugflow.db.errors import BugflowDatabaseError
from bugflow.logging_config import Redactor
from bugflow.services.errors import ServiceError

_secrets: list[str] = []


def register_secrets(secrets: list[str]) -> None:
    """Remember secret values so unexpected-error text can be redacted."""
    _secrets[:] = secrets


def echo(line: str) -> None:
    typer.echo(line)


def echo_error(line: str) -> None:
    typer.echo(line, err=True)


def confirm_typed(prompt: str, expected: str = "yes") -> bool:
    """Ask for a typed answer; end of input or any other answer means no."""
    typer.echo(f"{prompt} ", nl=False)
    stream = sys.stdin
    try:
        answer = stream.readline() if stream is not None else ""
    except (OSError, ValueError):
        answer = ""
    if not answer:
        typer.echo("")
    return answer.strip().lower() == expected


def error_message(exc: BaseException) -> str:
    """The text the CLI prints for an error. Never a stack trace or settings."""
    if isinstance(exc, ConfigError | BugflowDatabaseError | ServiceError):
        return str(exc)
    return f"Unexpected error: {Redactor(_secrets).redact(str(exc) or type(exc).__name__)}"


def fail(message: str, code: int = 1) -> typer.Exit:
    echo_error(message)
    return typer.Exit(code)


def guarded(func: Callable[..., Any]) -> Callable[..., Any]:
    """Map exceptions raised by a command to a one-line message and exit code 1."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except typer.Exit:
            raise
        except Exception as exc:
            raise fail(error_message(exc)) from None

    return wrapper
