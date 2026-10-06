"""Docker Compose checks. Run only with `uv run pytest -m integration`."""

import json
import socket
import subprocess
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def compose(monkeypatch):
    project = f"bugflow_it_{uuid.uuid4().hex[:8]}"
    port = _free_port()
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("POSTGRES_PORT", str(port))

    def run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=check,
        )

    run.port = port
    yield run
    run("down", "-v", check=False)


def _psql(compose, sql: str) -> str:
    result = compose("exec", "-T", "db", "psql", "-U", "bugflow", "-d", "bugflow", "-tA", "-c", sql)
    return result.stdout.strip()


def test_db_becomes_healthy(compose):
    compose("up", "-d", "--wait")
    services = [json.loads(line) for line in compose("ps", "--format", "json").stdout.splitlines()]
    assert len(services) == 1
    assert services[0]["Service"] == "db"
    assert services[0]["Health"] == "healthy"
    assert services[0]["Image"] == "pgvector/pgvector:pg17"


def test_port_bound_to_loopback(compose):
    compose("up", "-d", "--wait")
    assert compose("port", "db", "5432").stdout.strip() == f"127.0.0.1:{compose.port}"


def test_port_follows_postgres_port(compose):
    compose("up", "-d", "--wait")
    assert compose("port", "db", "5432").stdout.strip().endswith(f":{compose.port}")


def test_data_survives_down_and_up(compose):
    compose("up", "-d", "--wait")
    _psql(
        compose,
        "CREATE TABLE f01_persistence_probe (id int); INSERT INTO f01_persistence_probe VALUES (1)",
    )
    compose("down")
    compose("up", "-d", "--wait")
    assert _psql(compose, "SELECT count(*) FROM f01_persistence_probe") == "1"


def test_pgvector_available(compose):
    compose("up", "-d", "--wait")
    assert (
        _psql(compose, "SELECT name FROM pg_available_extensions WHERE name = 'vector'") == "vector"
    )
