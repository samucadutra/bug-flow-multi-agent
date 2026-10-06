"""Compose profile `nopgvector`. Run only with `uv run pytest -m integration`."""

import json
import os
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
    project = f"bugflow_plain_it_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", project)
    monkeypatch.setenv("POSTGRES_PORT", str(_free_port()))

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["docker", "compose", *args],
            cwd=ROOT,
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            check=True,
        )

    yield run
    subprocess.run(
        ["docker", "compose", "--profile", "nopgvector", "down", "-v"],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
    )


def test_default_up_starts_only_db(compose):
    assert compose("config", "--services").stdout.split() == ["db"]
    compose("up", "-d", "--wait")
    services = [json.loads(line) for line in compose("ps", "--format", "json").stdout.splitlines()]
    assert [service["Service"] for service in services] == ["db"]


def test_profile_service_is_loopback_and_ephemeral(compose):
    compose("--profile", "nopgvector", "up", "-d", "--wait", "db_plain")
    address = compose("port", "db_plain", "5432").stdout.strip()
    host, _, port = address.rpartition(":")
    assert host == "127.0.0.1"
    assert port != "5432"


def test_plain_server_lacks_vector(compose):
    compose("--profile", "nopgvector", "up", "-d", "--wait", "db_plain")
    result = compose(
        "exec",
        "-T",
        "db_plain",
        "psql",
        "-U",
        "bugflow",
        "-d",
        "bugflow",
        "-tA",
        "-c",
        "SELECT name FROM pg_available_extensions WHERE name = 'vector'",
    )
    assert result.stdout.strip() == ""
