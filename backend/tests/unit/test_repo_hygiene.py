import ast
import re
import subprocess
from pathlib import Path

from bugflow.config import Settings

ROOT = Path(__file__).resolve().parents[3]

EXPECTED = {
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OPENAI_EMBEDDING_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "SIMILAR_BUGS_K",
    "API_HOST",
    "API_PORT",
    "CORS_ORIGINS",
    "LOG_LEVEL",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "NEXT_PUBLIC_API_BASE_URL",
}


def _env_example() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, _, value = line.partition("=")
            values[name] = value
    return values


def test_env_example_lists_all_variables():
    assert set(_env_example()) == EXPECTED


def test_env_example_has_no_secret():
    values = _env_example()
    assert values["OPENAI_API_KEY"] == ""
    assert values["POSTGRES_PASSWORD"] == "bugflow"
    for value in values.values():
        assert not re.search(r"sk-[A-Za-z0-9_\-]{16,}", value)
        match = re.search(r"://[^:/@]+:([^@]+)@", value)
        if match:
            assert match.group(1) == "bugflow"


def test_env_is_git_ignored():
    def check(name: str) -> int:
        return subprocess.run(["git", "check-ignore", "-q", name], cwd=ROOT).returncode

    assert check(".env") == 0
    assert check(".env.example") == 1


def test_env_example_matches_settings_fields():
    fields = {name.upper() for name in Settings.model_fields}
    backend = EXPECTED - {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "POSTGRES_PORT",
        "NEXT_PUBLIC_API_BASE_URL",
    }
    assert backend == fields


def test_only_config_reads_environment():
    offenders = []
    for path in (ROOT / "backend" / "src").rglob("*.py"):
        if path.name == "config.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}:
                offenders.append(str(path))
            if isinstance(node, ast.Name) and node.id in {"environ", "getenv"}:
                offenders.append(str(path))
            if isinstance(node, ast.ImportFrom | ast.Import):
                names = [a.name for a in node.names] + [getattr(node, "module", "") or ""]
                if any("dotenv" in n for n in names):
                    offenders.append(str(path))
    assert offenders == []
