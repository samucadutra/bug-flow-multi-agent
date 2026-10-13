"""Error model and exception handlers: one JSON envelope, fixed messages, no stack traces."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from bugflow.config import ConfigError
from bugflow.db.errors import (
    BugflowDatabaseError,
    DatabaseUnavailableError,
    PgvectorUnavailableError,
)
from bugflow.logging_config import Redactor
from bugflow.services.errors import (
    EmptySearchTextError,
    FieldError,
    NotFoundError,
    SchemaNotInitializedError,
    ServiceError,
    StateConflictError,
    ValidationFailedError,
)
from bugflow.services.llm_client import LlmError

logger = logging.getLogger("bugflow.api")

INTERNAL_MESSAGE = "Internal server error"
VALIDATION_MESSAGE = "Validation failed"
BAD_JSON_MESSAGE = "Malformed JSON body"
UNDEFINED_TABLE = "42P01"

_HTTP_CODES = {
    400: ("bad_request", "Bad request"),
    404: ("not_found", "Not found"),
    405: ("method_not_allowed", "Method not allowed"),
}


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ApiError(BaseModel):
    """The only error shape the API returns."""

    error: ErrorBody


def error_response(
    status: int, code: str, message: str, details: list[ErrorDetail] | None = None
) -> JSONResponse:
    body = ApiError(error=ErrorBody(code=code, message=message, details=details or []))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def _expected(error: dict[str, Any]) -> str:
    expected = str((error.get("ctx") or {}).get("expected", ""))
    return ", ".join(part.strip().strip("'") for part in expected.split(","))


def _message(error: dict[str, Any]) -> str:
    """A fixed message for one request validation error; the input value is never echoed."""
    kind = error["type"]
    ctx = error.get("ctx") or {}
    if kind == "missing":
        return "is required"
    if kind == "extra_forbidden":
        return "is not allowed"
    if kind in ("enum", "literal_error"):
        return f"must be one of: {_expected(error)}"
    if kind in ("int_parsing", "int_type", "int_from_float"):
        return "must be an integer"
    if kind in ("bool_parsing", "bool_type"):
        return "must be a boolean"
    if kind == "less_than_equal":
        return f"must be at most {ctx.get('le')}"
    if kind == "greater_than_equal":
        return f"must be at least {ctx.get('ge')}"
    if kind in ("string_too_short", "blank_text"):
        return "must not be empty"
    if kind == "string_too_long":
        return f"must be at most {ctx.get('max_length')} characters"
    if kind in ("dict_type", "model_attributes_type", "model_type"):
        return "must be a JSON object"
    if kind in CUSTOM_MESSAGE_TYPES:
        return str(error["msg"])
    return "is invalid"


# Pydantic custom error types whose message is written by this package.
CUSTOM_MESSAGE_TYPES = frozenset({"confirm_required", "target_required"})


def _field(error: dict[str, Any]) -> str:
    loc = [str(part) for part in error["loc"]]
    return loc[1] if len(loc) > 1 else (loc[0] if loc else "body")


def validation_details(errors: list[dict[str, Any]]) -> list[ErrorDetail]:
    return [ErrorDetail(field=_field(error), message=_message(error)) for error in errors]


def field_details(field_errors: list[FieldError]) -> list[ErrorDetail]:
    return [ErrorDetail(field=item.field, message=item.message) for item in field_errors]


def _is_malformed_json(exc: RequestValidationError) -> bool:
    return any(error["type"] == "json_invalid" for error in exc.errors())


def install_error_handlers(app: FastAPI, redactor: Redactor) -> None:
    """Register the handlers of the status mapping; unexpected errors use the middleware below."""

    def respond(status: int, code: str, message: str) -> JSONResponse:
        return error_response(status, code, redactor.redact(message))

    def unavailable(message: str) -> JSONResponse:
        return respond(503, "service_unavailable", message)

    @app.exception_handler(ValidationFailedError)
    async def _validation_failed(request: Request, exc: ValidationFailedError) -> JSONResponse:
        return error_response(
            422, "validation_error", VALIDATION_MESSAGE, field_details(exc.field_errors)
        )

    @app.exception_handler(EmptySearchTextError)
    async def _empty_search(request: Request, exc: EmptySearchTextError) -> JSONResponse:
        return error_response(
            422,
            "validation_error",
            VALIDATION_MESSAGE,
            [ErrorDetail(field="q", message="must not be empty")],
        )

    @app.exception_handler(RequestValidationError)
    async def _request_invalid(request: Request, exc: RequestValidationError) -> JSONResponse:
        if _is_malformed_json(exc):
            return error_response(400, "bad_request", BAD_JSON_MESSAGE)
        return error_response(
            422,
            "validation_error",
            VALIDATION_MESSAGE,
            validation_details([dict(error) for error in exc.errors()]),
        )

    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return respond(404, "not_found", exc.message)

    @app.exception_handler(StateConflictError)
    async def _conflict(request: Request, exc: StateConflictError) -> JSONResponse:
        return respond(409, "state_conflict", exc.message)

    @app.exception_handler(SchemaNotInitializedError)
    async def _not_initialized(request: Request, exc: SchemaNotInitializedError) -> JSONResponse:
        return respond(409, "state_conflict", exc.message)

    @app.exception_handler(DatabaseUnavailableError)
    async def _database_down(request: Request, exc: DatabaseUnavailableError) -> JSONResponse:
        return unavailable(str(exc))

    @app.exception_handler(PgvectorUnavailableError)
    async def _pgvector_down(request: Request, exc: PgvectorUnavailableError) -> JSONResponse:
        return unavailable(str(exc))

    @app.exception_handler(LlmError)
    async def _llm_down(request: Request, exc: LlmError) -> JSONResponse:
        return unavailable(exc.message)

    @app.exception_handler(ConfigError)
    async def _config(request: Request, exc: ConfigError) -> JSONResponse:
        return unavailable(exc.message)

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def _driver_down(request: Request, exc: Exception) -> JSONResponse:
        return unavailable(str(DatabaseUnavailableError()))

    @app.exception_handler(ProgrammingError)
    async def _programming(request: Request, exc: ProgrammingError) -> JSONResponse:
        if getattr(exc.orig, "sqlstate", None) == UNDEFINED_TABLE:
            return respond(409, "state_conflict", SchemaNotInitializedError().message)
        logger.error("Database error: %s", redactor.redact(type(exc).__name__))
        return respond(500, "internal_error", INTERNAL_MESSAGE)

    @app.exception_handler(BugflowDatabaseError)
    async def _database_error(request: Request, exc: BugflowDatabaseError) -> JSONResponse:
        return unavailable(str(exc))

    @app.exception_handler(ServiceError)
    async def _service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return respond(500, "internal_error", exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_CODES.get(exc.status_code, ("internal_error", "Request failed"))
        if exc.status_code not in _HTTP_CODES and exc.status_code < 500:
            code = "bad_request"
        return error_response(exc.status_code, code, message)


class UnexpectedErrorMiddleware:
    """Turns any unhandled exception into the generic `500`; the redacted text goes to the log."""

    def __init__(self, app: ASGIApp, redactor: Redactor) -> None:
        self.app = app
        self._redactor = redactor

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            text = self._redactor.redact(str(exc) or type(exc).__name__)
            logger.error(
                "Unhandled error on %s %s: %s", scope.get("method"), scope.get("path"), text
            )
            if started:
                return
            response = error_response(500, "internal_error", INTERNAL_MESSAGE)
            await response(scope, receive, send)
