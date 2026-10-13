"""Status mapping, fixed messages and redaction of `bugflow.api.errors`."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from bugflow.api.errors import UnexpectedErrorMiddleware, install_error_handlers
from bugflow.config import ConfigError
from bugflow.db.errors import DatabaseUnavailableError, PgvectorUnavailableError
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
from bugflow.services.reopen import ReopenFailedError
from bugflow.services.reports import ReportRenderError

CASES = [
    (ValidationFailedError([FieldError(field="t", message="bad")]), 422, "validation_error"),
    (EmptySearchTextError(), 422, "validation_error"),
    (NotFoundError("Bug 1 not found"), 404, "not_found"),
    (StateConflictError("Bug 1 is not open and cannot be edited"), 409, "state_conflict"),
    (SchemaNotInitializedError(), 409, "state_conflict"),
    (DatabaseUnavailableError(), 503, "service_unavailable"),
    (PgvectorUnavailableError(), 503, "service_unavailable"),
    (LlmError("OpenAI authentication failed"), 503, "service_unavailable"),
    (ConfigError("OPENAI_API_KEY", "OPENAI_API_KEY is not set"), 503, "service_unavailable"),
    (OperationalError("SELECT 1", {}, Exception("password=hunter2")), 503, "service_unavailable"),
    (ReopenFailedError(3), 500, "internal_error"),
    (ReportRenderError("Report rendering failed: boom"), 500, "internal_error"),
    (ServiceError("Something fixed"), 500, "internal_error"),
]  # fmt: skip


def build_app(error: Exception, secret: str = "sk-canary") -> FastAPI:
    app = FastAPI()
    redactor = Redactor([secret])

    @app.get("/boom")
    def boom() -> None:
        raise error

    @app.post("/json")
    def json_body(payload: dict) -> dict:
        return payload

    install_error_handlers(app, redactor)
    app.add_middleware(UnexpectedErrorMiddleware, redactor=redactor)
    return app


@pytest.mark.parametrize(("error", "status", "code"), CASES)
def test_service_errors_map_to_status_and_code(error, status, code):
    response = TestClient(build_app(error)).get("/boom")
    assert response.status_code == status
    body = response.json()["error"]
    assert body["code"] == code
    assert set(body) == {"code", "message", "details"}


def test_validation_details_carry_fields():
    error = ValidationFailedError([FieldError(field="title", message="is required")])
    body = TestClient(build_app(error)).get("/boom").json()["error"]
    assert body["details"] == [{"field": "title", "message": "is required"}]


def test_empty_search_reports_field_q():
    body = TestClient(build_app(EmptySearchTextError())).get("/boom").json()["error"]
    assert body["details"] == [{"field": "q", "message": "must not be empty"}]


def test_database_message_is_fixed_and_has_no_driver_text():
    error = OperationalError("SELECT 1", {}, Exception("password=hunter2"))
    response = TestClient(build_app(error)).get("/boom")
    assert response.json()["error"]["message"] == "Cannot connect to the database"
    assert "hunter2" not in response.text


def test_unhandled_error_is_generic_and_redacted(caplog):
    error = RuntimeError("failure with sk-canary inside")
    client = TestClient(build_app(error), raise_server_exceptions=False)
    with caplog.at_level("ERROR", logger="bugflow.api"):
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"] == {
        "code": "internal_error",
        "message": "Internal server error",
        "details": [],
    }
    assert "sk-canary" not in response.text
    assert "Traceback" not in response.text
    assert "sk-canary" not in caplog.text
    assert "failure with" in caplog.text


def test_service_error_text_is_redacted():
    response = TestClient(build_app(ServiceError("leaked sk-canary"))).get("/boom")
    assert "sk-canary" not in response.text


def test_unknown_route_and_method():
    client = TestClient(build_app(RuntimeError("x")), raise_server_exceptions=False)
    missing = client.get("/nope")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    wrong = client.post("/boom")
    assert wrong.status_code == 405
    assert wrong.json()["error"]["code"] == "method_not_allowed"


def test_malformed_json_is_bad_request():
    response = TestClient(build_app(RuntimeError("x"))).post(
        "/json", content="{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "bad_request"


def test_missing_body_reports_field_body():
    response = TestClient(build_app(RuntimeError("x"))).post("/json")
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "body"
