"""The parity map and the gap finder."""

from __future__ import annotations

import typer

from bugflow.api import create_app
from bugflow.api.parity import EXCLUDED, PARITY, cli_leaf_commands, find_parity_gaps, route_table
from bugflow.cli import app as cli_app

URL = "postgresql+psycopg://bugflow:pw@127.0.0.1:1/bugflow"


def test_real_app_has_no_gaps(make_settings):
    routes = route_table(create_app(make_settings(DATABASE_URL=URL)))
    assert find_parity_gaps(cli_app, routes) == []


def test_leaf_commands_are_nine_plus_serve():
    leaves = set(cli_leaf_commands(cli_app))
    assert leaves == set(PARITY) | EXCLUDED
    assert len(PARITY) == 9
    assert EXCLUDED == {"serve"}


def test_parity_gap_detected(make_settings):
    extended = typer.Typer()
    extended.registered_commands.extend(cli_app.registered_commands)
    extended.registered_groups.extend(cli_app.registered_groups)
    extended.callback()(lambda: None)

    @extended.command("export")
    def export() -> None:
        """Export bugs."""

    routes = route_table(create_app(make_settings(DATABASE_URL=URL)))
    gaps = find_parity_gaps(extended, routes)
    assert len(gaps) == 1
    assert "export" in gaps[0]
    assert "no registered API route" in gaps[0]


def test_missing_route_is_a_gap():
    routes = {route for command, route in PARITY.items() if command != "search"}
    gaps = find_parity_gaps(cli_app, routes)
    assert gaps == ["Command 'search' has no registered API route"]
