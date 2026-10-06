"""`bugflow search`: find the bugs most similar to a text."""

from __future__ import annotations

import typer

from bugflow.cli.context import bootstrap
from bugflow.cli.output import echo, guarded
from bugflow.db.engine import session_factory
from bugflow.services.similarity import DEFAULT_SEARCH_LIMIT, search_similar

HEADER = "SCORE  ID  TITLE  STATUS"


@guarded
def search(
    text: str = typer.Argument(..., help="Text to search for."),
    limit: int = typer.Option(
        DEFAULT_SEARCH_LIMIT, "--limit", help="Number of results to show (1 to 20)."
    ),
) -> None:
    context = bootstrap()
    try:
        with session_factory(context.engine)() as session:
            result = search_similar(session, context.get_client, text, limit)
    finally:
        context.close()
    if result.hint:
        echo(result.hint)
        return
    echo(HEADER)
    for item in result.items:
        echo(f"{item.score:.2f}  {item.bug_id}  {item.title}  {item.status}")


def register(app: typer.Typer) -> None:
    app.command("search", help="Search for bugs similar to a text.")(search)
