"""`bugflow check`: report database, vector search and LLM health."""

from __future__ import annotations

import typer

from bugflow.cli.context import bootstrap
from bugflow.cli.output import echo, guarded
from bugflow.services.health import check_health


@guarded
def check() -> None:
    context = bootstrap()
    try:
        report = check_health(context.settings, context.engine)
    finally:
        context.close()
    for line in report.lines():
        echo(line)
    if not report.all_ok:
        raise typer.Exit(1)


def register(app: typer.Typer) -> None:
    app.command("check", help="Check the database, vector search and LLM connection.")(check)
