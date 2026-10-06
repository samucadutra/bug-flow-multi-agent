"""Command line application: a Typer app plus an ordered registry of command modules."""

from __future__ import annotations

import typer

from bugflow import __version__
from bugflow.cli.commands import check, db, index, search, triage

# Later features add their module here (F07: report; F08: reopen).
COMMAND_MODULES = (check, db, index, search, triage)

app = typer.Typer(
    name="bugflow",
    help="BugFlow: multi-agent bug triage command line tool.",
    add_completion=False,
    no_args_is_help=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"bugflow {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the BugFlow version and exit.",
    ),
) -> None:
    """BugFlow: multi-agent bug triage command line tool."""


for _module in COMMAND_MODULES:
    _module.register(app)


def main() -> None:
    app()
