"""OpenAPI document and route table."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bugflow.api import create_app
from bugflow.api.parity import route_table

URL = "postgresql+psycopg://bugflow:pw@127.0.0.1:1/bugflow"
PREFIX = "/api/v1"

EXPECTED = {
    ("GET", "/health"),
    ("GET", "/meta/enums"),
    ("GET", "/stats"),
    ("POST", "/admin/db/init"),
    ("POST", "/admin/db/seed"),
    ("POST", "/admin/db/reset"),
    ("POST", "/admin/index"),
    ("GET", "/bugs"),
    ("POST", "/bugs"),
    ("GET", "/bugs/{id}"),
    ("PATCH", "/bugs/{id}"),
    ("GET", "/bugs/{id}/similar"),
    ("GET", "/bugs/{id}/runs"),
    ("POST", "/bugs/{id}/reopen"),
    ("GET", "/bugs/{id}/report"),
    ("GET", "/search"),
    ("POST", "/triage-runs"),
    ("GET", "/runs"),
    ("GET", "/runs/{id}"),
    ("GET", "/runs/{id}/events"),
}


@pytest.fixture
def app(make_settings):
    return create_app(make_settings(DATABASE_URL=URL, OPENAI_API_KEY="sk-test-canary-1234567890"))


def test_route_table_has_the_twenty_endpoints(app):
    assert route_table(app) >= {(method, PREFIX + path) for method, path in EXPECTED}
    api_routes = {route for route in route_table(app) if route[1].startswith(PREFIX)}
    assert len(api_routes) == 20


def test_openapi_lists_every_endpoint(app):
    document = TestClient(app).get("/openapi.json").json()
    found = {(method.upper(), path) for path, item in document["paths"].items() for method in item}
    assert found == {(method, PREFIX + path) for method, path in EXPECTED}


def test_docs_page_references_openapi(app):
    response = TestClient(app).get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/openapi.json" in response.text


def test_openapi_has_no_configured_value(app):
    text = TestClient(app).get("/openapi.json").text
    assert "sk-test-canary" not in text
    assert "127.0.0.1:1" not in text
    assert "pw@" not in text
