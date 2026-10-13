"""CORS: only the configured origin is allowed."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from bugflow.api import create_app

ALLOWED = "http://localhost:3000"
OTHER = "http://evil.example"
URL = "postgresql+psycopg://bugflow:pw@127.0.0.1:1/bugflow"


@pytest.fixture
def client(make_settings):
    app = create_app(make_settings(DATABASE_URL=URL))
    return TestClient(app)


def test_allowed_origin_gets_header(client):
    response = client.get("/api/v1/meta/enums", headers={"Origin": ALLOWED})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED


def test_other_origin_gets_no_header(client):
    response = client.get("/api/v1/meta/enums", headers={"Origin": OTHER})
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_other_origin_is_refused(client):
    response = client.options(
        "/api/v1/bugs",
        headers={"Origin": OTHER, "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_preflight_from_allowed_origin_lists_methods_and_headers(client):
    response = client.options(
        "/api/v1/bugs",
        headers={
            "Origin": ALLOWED,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert "access-control-allow-credentials" not in response.headers


def test_configured_origin_replaces_default(make_settings):
    app = create_app(make_settings(DATABASE_URL=URL, CORS_ORIGINS="http://app.example"))
    client = TestClient(app)
    ok = client.get("/api/v1/meta/enums", headers={"Origin": "http://app.example"})
    assert ok.headers["access-control-allow-origin"] == "http://app.example"
    denied = client.get("/api/v1/meta/enums", headers={"Origin": ALLOWED})
    assert "access-control-allow-origin" not in denied.headers
