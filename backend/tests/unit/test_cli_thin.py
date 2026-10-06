import ast
import sys
from pathlib import Path

import bugflow

CLI_DIR = Path(bugflow.__file__).parent / "cli"
ALLOWED_PREFIXES = (
    "typer",
    "bugflow.config",
    "bugflow.logging_config",
    "bugflow.db.engine",
    "bugflow.db.errors",
    "bugflow.services",
    "bugflow.cli",
    "bugflow",
)
FORBIDDEN = ("sqlalchemy", "alembic", "openai", "bugflow.db.models")


def imported_modules(path: Path) -> list[str]:
    modules = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
    return modules


def is_allowed(module: str) -> bool:
    root = module.split(".")[0]
    if root in sys.stdlib_module_names or root == "__future__":
        return True
    if module == "bugflow":
        return True
    return any(
        module == p or module.startswith(f"{p}.") for p in ALLOWED_PREFIXES if p != "bugflow"
    )


def test_cli_modules_import_only_allowed_packages():
    paths = sorted(CLI_DIR.rglob("*.py"))
    assert paths
    for path in paths:
        for module in imported_modules(path):
            assert not module.startswith(FORBIDDEN), f"{path.name} imports {module}"
            assert is_allowed(module), f"{path.name} imports {module}"


def test_every_command_module_uses_services():
    commands = [p for p in (CLI_DIR / "commands").glob("*.py") if p.name != "__init__.py"]
    assert commands
    for path in commands:
        assert any(m.startswith("bugflow.services") for m in imported_modules(path)), path.name
