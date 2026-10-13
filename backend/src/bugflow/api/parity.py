"""CLI to API parity: the machine-checked map and the gap finder used by the parity test."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

import typer
from fastapi import FastAPI

from bugflow.api.app import API_PREFIX

# CLI command path -> (HTTP method, absolute path) of the route with the same effect.
PARITY: dict[str, tuple[str, str]] = {
    "check": ("GET", f"{API_PREFIX}/health"),
    "db init": ("POST", f"{API_PREFIX}/admin/db/init"),
    "db seed": ("POST", f"{API_PREFIX}/admin/db/seed"),
    "db reset": ("POST", f"{API_PREFIX}/admin/db/reset"),
    "index": ("POST", f"{API_PREFIX}/admin/index"),
    "search": ("GET", f"{API_PREFIX}/search"),
    "triage": ("POST", f"{API_PREFIX}/triage-runs"),
    "reopen": ("POST", f"{API_PREFIX}/bugs/{{id}}/reopen"),
    "report": ("GET", f"{API_PREFIX}/bugs/{{id}}/report"),
}

# Commands that have no API route by design.
EXCLUDED: frozenset[str] = frozenset({"serve"})

Route = tuple[str, str]


def cli_leaf_commands(cli_app: typer.Typer) -> list[str]:
    """Every leaf command of the Typer app as a space-joined path, in registry order."""

    def walk(command: Any, prefix: list[str]) -> Iterator[str]:
        children = getattr(command, "commands", None)
        if children is not None:
            for name, child in children.items():
                yield from walk(child, [*prefix, name])
        else:
            yield " ".join(prefix)

    root = typer.main.get_command(cli_app)
    return list(walk(root, []))


def route_table(app: FastAPI) -> set[Route]:
    """The (METHOD, path) pairs of the application, read from its OpenAPI document.

    FastAPI resolves the router tree lazily, so the document is the stable listing.
    """
    paths = app.openapi().get("paths", {})
    return {(method.upper(), path) for path, item in paths.items() for method in item}


def find_parity_gaps(cli_app: typer.Typer, routes: Iterable[Route]) -> list[str]:
    """One message per CLI command that is neither excluded nor mapped to a registered route."""
    registered = set(routes)
    gaps: list[str] = []
    for command in cli_leaf_commands(cli_app):
        if command in EXCLUDED:
            continue
        target = PARITY.get(command)
        if target is None or target not in registered:
            gaps.append(f"Command '{command}' has no registered API route")
    return gaps
