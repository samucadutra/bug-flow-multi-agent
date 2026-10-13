"""`bugflow serve` as a child process."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from mocks.fake_openai_server import VALID_KEY

pytestmark = pytest.mark.integration

BACKEND = Path(__file__).resolve().parents[2]
BINARY = Path(sys.executable).parent / "bugflow"
DEAD_URL = "postgresql+psycopg://bugflow:dead-pw@127.0.0.1:1/bugflow"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class Server:
    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self.lines: list[str] = []
        self._banner = threading.Event()
        self._thread = threading.Thread(target=self._pump, daemon=True)
        self._thread.start()

    def _pump(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.lines.append(line.rstrip("\n"))
            if line.startswith("Serving BugFlow API"):
                self._banner.set()

    def wait_banner(self, timeout: float = 60) -> str:
        assert self._banner.wait(timeout), "no banner: " + "\n".join(self.lines)
        return next(line for line in self.lines if line.startswith("Serving BugFlow API"))

    def get(self, url: str) -> httpx.Response:
        deadline = time.monotonic() + 30
        while True:
            try:
                return httpx.get(url, timeout=5)
            except httpx.TransportError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)

    @property
    def output(self) -> str:
        return "\n".join(self.lines)


@pytest.fixture
def spawn(test_engine, stand_in) -> Iterator[Callable[..., Server]]:
    servers: list[Server] = []
    url = test_engine.url.render_as_string(hide_password=False)

    def start(*args: str, env: dict[str, str | None] | None = None) -> Server:
        base = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("DATABASE_", "TEST_DATABASE_", "OPENAI_", "API_", "CORS_"))
        }
        base.update(
            DATABASE_URL=url, OPENAI_BASE_URL=stand_in.base_url, OPENAI_API_KEY=VALID_KEY, TZ="UTC"
        )
        for name, value in (env or {}).items():
            if value is None:
                base.pop(name, None)
            else:
                base[name] = value
        process = subprocess.Popen(
            [str(BINARY), "serve", *args],
            cwd=BACKEND,
            env=base,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        server = Server(process)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.process.terminate()
        try:
            server.process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            server.process.kill()


def test_custom_port_from_the_environment(spawn):
    port = free_port()
    server = spawn(env={"API_PORT": str(port)})
    assert f"http://127.0.0.1:{port}" in server.wait_banner()
    assert server.get(f"http://127.0.0.1:{port}/docs").status_code == 200
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) == 0


def test_host_and_port_options_and_clean_shutdown(spawn):
    port = free_port()
    server = spawn("--host", "127.0.0.1", "--port", str(port))
    assert "docs at /docs" in server.wait_banner()
    assert server.get(f"http://127.0.0.1:{port}/api/v1/health").status_code == 200
    server.process.terminate()
    assert server.process.wait(timeout=30) == 0


def test_starts_without_a_key(spawn):
    port = free_port()
    server = spawn(env={"API_PORT": str(port), "OPENAI_API_KEY": None})
    server.wait_banner()
    response = server.get(f"http://127.0.0.1:{port}/api/v1/health")
    assert response.status_code == 200
    assert response.json()["llm"]["message"] == "OPENAI_API_KEY is not set"
    assert server.process.poll() is None


def test_missing_database_url_fails_fast(spawn):
    port = free_port()
    server = spawn(env={"DATABASE_URL": None, "API_PORT": str(port)})
    assert server.process.wait(timeout=60) == 1
    server._thread.join(timeout=5)
    assert "DATABASE_URL is missing or invalid" in server.output
    with socket.socket() as sock:
        assert sock.connect_ex(("127.0.0.1", port)) != 0


def test_database_down_at_start(spawn):
    port = free_port()
    server = spawn(env={"DATABASE_URL": DEAD_URL, "API_PORT": str(port)})
    server.wait_banner()
    assert server.get(f"http://127.0.0.1:{port}/docs").status_code == 200
    assert server.process.poll() is None
    assert "dead-pw" not in server.output
    assert DEAD_URL not in server.output


def test_non_loopback_host_prints_the_warning(spawn):
    port = free_port()
    server = spawn("--host", "0.0.0.0", "--port", str(port))
    server.wait_banner()
    server.get(f"http://127.0.0.1:{port}/docs")
    assert "no authentication" in server.output
