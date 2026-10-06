import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
SRC = BACKEND / "src"
PACKAGE = SRC / "bugflow"
VERSIONS = PACKAGE / "migrations" / "versions"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
        elif isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
    return modules


def test_seed_uses_application_models():
    assert "bugflow.db.models" in _imports(PACKAGE / "services" / "db_admin.py")
    for path in (PACKAGE / "seed" / "bugs.py", PACKAGE / "services" / "db_admin.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                assert name not in {"Column", "mapped_column"}, path
                assert name != "Table", path
        assert "CREATE TABLE" not in path.read_text()


def test_ddl_only_in_models_and_migrations():
    allowed = {PACKAGE / "db" / "models.py", PACKAGE / "db" / "base.py"}
    offenders = []
    for path in SRC.rglob("*.py"):
        if path in allowed or PACKAGE / "migrations" in path.parents:
            continue
        text = path.read_text()
        if "CREATE TABLE" in text or re.search(r"(?<![A-Za-z_])Table\(", text):
            offenders.append(path.name)
    assert offenders == []


def test_base_revision_creates_vector_extension():
    bases = []
    for path in VERSIONS.glob("*.py"):
        text = path.read_text()
        if re.search(r"^down_revision[^=]*=\s*None\s*$", text, re.MULTILINE):
            bases.append(text)
    assert len(bases) == 1
    assert "CREATE EXTENSION IF NOT EXISTS vector" in bases[0]


def test_migrations_env_reads_no_environment():
    tree = ast.parse((PACKAGE / "migrations" / "env.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "getenv"}
        if isinstance(node, ast.Name):
            assert node.id not in {"environ", "getenv"}
