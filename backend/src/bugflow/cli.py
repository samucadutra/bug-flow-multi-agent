"""Command line entry point (extended by later features)."""

from __future__ import annotations

import typer

from bugflow import __version__

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


def main() -> None:
    app()
