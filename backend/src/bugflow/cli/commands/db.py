"""`bugflow db init|seed|reset`: administrative database commands."""

from __future__ import annotations

import typer

from bugflow.cli.context import bootstrap
from bugflow.cli.output import confirm_typed, echo, guarded
from bugflow.services.operations import (
    init_messages,
    run_init,
    run_reset,
    run_seed,
    seed_message,
)

db_app = typer.Typer(
    help="Create, load and reset the database.", no_args_is_help=True, add_completion=False
)

RESET_PROMPT = "This deletes all data. Type 'yes' to continue:"


@guarded
def init() -> None:
    context = bootstrap()
    try:
        result = run_init(context.engine, context.redactor)
    finally:
        context.close()
    for line in init_messages(result):
        echo(line)


@guarded
def seed() -> None:
    context = bootstrap()
    try:
        result = run_seed(context.engine, context.redactor)
    finally:
        context.close()
    echo(seed_message(result))


@guarded
def reset(
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    if not yes and not confirm_typed(RESET_PROMPT):
        echo("Aborted: nothing was deleted")
        raise typer.Exit(1)
    context = bootstrap()
    try:
        run_reset(context.engine, context.redactor)
    finally:
        context.close()
    echo("Database reset: schema recreated, no data loaded")


def register(app: typer.Typer) -> None:
    db_app.command("init", help="Apply database migrations.")(init)
    db_app.command("seed", help="Load the sample bugs.")(seed)
    db_app.command("reset", help="Delete all data and recreate an empty schema.")(reset)
    app.add_typer(db_app, name="db")
