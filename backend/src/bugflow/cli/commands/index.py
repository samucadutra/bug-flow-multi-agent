"""`bugflow index`: rebuild the embedding of every bug."""

from __future__ import annotations

import typer

from bugflow.cli.context import bootstrap
from bugflow.cli.output import echo, guarded
from bugflow.services.operations import index_message, run_index


@guarded
def index() -> None:
    context = bootstrap()
    try:
        result = run_index(context.engine, context.get_client, context.redactor)
    finally:
        context.close()
    echo(index_message(result))


def register(app: typer.Typer) -> None:
    app.command("index", help="Build or rebuild the embedding index of all bugs.")(index)
