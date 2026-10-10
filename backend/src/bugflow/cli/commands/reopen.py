"""`bugflow reopen`: return a processed or failed bug to open after a typed confirmation."""

from __future__ import annotations

import typer

from bugflow.cli.context import bootstrap
from bugflow.cli.output import confirm_typed, echo, guarded
from bugflow.services.reopen import reopen_bug


def reopen_prompt(bug_id: int) -> str:
    return f"This deletes the results and report of bug {bug_id}. Type 'yes' to continue:"


@guarded
def reopen(
    bug_id: int = typer.Argument(..., help="Id of the bug to reopen."),
    yes: bool = typer.Option(False, "--yes", help="Skip the confirmation prompt."),
) -> None:
    if not yes and not confirm_typed(reopen_prompt(bug_id)):
        echo("Aborted: nothing was deleted")
        raise typer.Exit(1)
    context = bootstrap()
    try:
        reopen_bug(context.engine, bug_id)
    finally:
        context.close()
    echo(f"Bug {bug_id} reopened")


def register(app: typer.Typer) -> None:
    app.command("reopen", help="Return a processed or failed bug to open and delete its results.")(
        reopen
    )
