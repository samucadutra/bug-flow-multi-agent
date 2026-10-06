"""Structured logging with secret redaction."""

from __future__ import annotations

import logging
import re
import sys
import time
from typing import TextIO

from bugflow.config import MASK, Settings

LOGGER_ROOT = "bugflow"
_HANDLER_MARK = "_bugflow_handler"
_URL_PASSWORD_RE = re.compile(r"(://[^/\s:@]*:)([^@\s]+)(@)")
_SK_TOKEN_RE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")


class Redactor:
    """Masks known secret values and secret-shaped text."""

    def __init__(self, secrets: list[str] | None = None) -> None:
        unique = {secret for secret in (secrets or []) if secret}
        self._secrets = sorted(unique, key=len, reverse=True)

    def redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, MASK)
        text = _URL_PASSWORD_RE.sub(rf"\g<1>{MASK}\g<3>", text)
        return _SK_TOKEN_RE.sub(MASK, text)


class RedactingFilter(logging.Filter):
    """Redacts the interpolated message, exception text and stack text of each record."""

    def __init__(self, redactor: Redactor) -> None:
        super().__init__()
        self._redactor = redactor
        self._plain = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redactor.redact(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = self._redactor.redact(self._plain.formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = self._redactor.redact(record.exc_text)
        if record.stack_info:
            record.stack_info = self._redactor.redact(record.stack_info)
        return True


class RunFormatter(logging.Formatter):
    """`<UTC timestamp> <LEVEL> [run=<id>] <message>`; the run segment is optional."""

    converter = time.gmtime

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", self.converter(record.created))

    def format(self, record: logging.LogRecord) -> str:
        run_id = getattr(record, "run_id", None)
        run = f" [run={run_id}]" if run_id is not None else ""
        line = f"{self.formatTime(record)} {record.levelname}{run} {record.getMessage()}"
        if record.exc_text:
            line = f"{line}\n{record.exc_text}"
        if record.stack_info:
            line = f"{line}\n{record.stack_info}"
        return line


def configure_logging(settings: Settings, stream: TextIO | None = None) -> None:
    """Configure the `bugflow` logger hierarchy. Safe to call repeatedly."""
    logger = logging.getLogger(LOGGER_ROOT)
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_MARK, False):
            logger.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    setattr(handler, _HANDLER_MARK, True)
    handler.setFormatter(RunFormatter())
    handler.addFilter(RedactingFilter(Redactor(settings.secret_values())))
    logger.addHandler(handler)
    logger.setLevel(settings.log_level)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    if name == LOGGER_ROOT or name.startswith(f"{LOGGER_ROOT}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_ROOT}.{name}")


def bind_run(logger: logging.Logger, run_id: int) -> logging.LoggerAdapter:
    return logging.LoggerAdapter(logger, {"run_id": run_id})
