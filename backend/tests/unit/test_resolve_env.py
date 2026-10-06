import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "resolve-env.sh"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repos(tmp_path):
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "commit", "-q", "--allow-empty", "-m", "init")
    linked = tmp_path / "linked"
    _git(main, "worktree", "add", "-q", str(linked), "-b", "feature")
    return main, linked


def _run(cwd: Path, *args: str, offset: str | None = None):
    env = {k: v for k, v in os.environ.items() if k != "APP_OFFSET"}
    if offset is not None:
        env["APP_OFFSET"] = offset
    return subprocess.run(
        [str(SCRIPT), *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def _parse(stdout: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in stdout.splitlines())


def test_main_checkout_values(repos):
    result = _run(repos[0])
    assert result.returncode == 0
    assert _parse(result.stdout) == {
        "APP_OFFSET": "0",
        "POSTGRES_PORT": "5432",
        "POSTGRES_DB": "bugflow",
        "COMPOSE_PROJECT_NAME": "bugflow",
        "API_PORT": "8000",
        "FRONTEND_PORT": "3000",
    }


def test_linked_worktree_values(repos):
    values = _parse(_run(repos[1]).stdout)
    n = int(values["APP_OFFSET"])
    assert 1 <= n <= 99
    assert values["POSTGRES_PORT"] == str(5432 + n)
    assert values["API_PORT"] == str(8000 + n)
    assert values["FRONTEND_PORT"] == str(3000 + n)
    assert values["POSTGRES_DB"] == f"bugflow_w{n}"
    assert values["COMPOSE_PROJECT_NAME"] == f"bugflow_w{n}"


def test_deterministic(repos):
    assert _run(repos[1]).stdout == _run(repos[1]).stdout


def test_offset_override(repos):
    values = _parse(_run(repos[0], offset="7").stdout)
    assert values["APP_OFFSET"] == "7"
    assert values["POSTGRES_PORT"] == "5439"
    assert values["API_PORT"] == "8007"
    assert values["FRONTEND_PORT"] == "3007"
    assert values["POSTGRES_DB"] == "bugflow_w7"
    assert values["COMPOSE_PROJECT_NAME"] == "bugflow_w7"


@pytest.mark.parametrize("bad", ["100", "abc", "-1", ""])
def test_invalid_override_rejected(repos, bad):
    result = _run(repos[0], offset=bad)
    assert result.returncode != 0
    assert "APP_OFFSET" in result.stderr
    assert result.stdout == ""


def test_export_flag(repos):
    plain = _run(repos[0]).stdout.splitlines()
    exported = _run(repos[0], "--export").stdout.splitlines()
    assert exported == [f"export {line}" for line in plain]


def test_outside_git_repository(tmp_path):
    result = _run(tmp_path)
    assert result.returncode != 0
    assert "git" in result.stderr
    assert result.stdout == ""
