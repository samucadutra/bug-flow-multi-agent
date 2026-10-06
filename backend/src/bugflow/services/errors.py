"""Typed service errors. Messages are fixed English text without secrets or URLs."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FieldError(BaseModel):
    """One rejected input field. The message never contains the offending value."""

    model_config = ConfigDict(frozen=True)

    field: str
    message: str


class ServiceError(Exception):
    """Base class of every error raised by the service layer."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ValidationFailedError(ServiceError):
    """Input rejected; carries one `FieldError` per rejected field."""

    def __init__(self, field_errors: list[FieldError]) -> None:
        super().__init__("Validation failed")
        self.field_errors = field_errors


class NotFoundError(ServiceError):
    """Unknown bug or run."""


class StateConflictError(ServiceError):
    """The requested change is not allowed in the current state."""


class SchemaNotInitializedError(ServiceError):
    def __init__(self) -> None:
        super().__init__("Database schema is not initialized; run 'bugflow db init'")
