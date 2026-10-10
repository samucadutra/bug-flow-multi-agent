"""`bugflow report`: print a bug's stored report or write it to a file."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated

import typer

from bugflow.cli.context import bootstrap
from bugflow.cli.output import echo, fail, guarded
from bugflow.db.engine import session_factory
from bugflow.services.reports import ReportFormat, get_report


def _write_file(path: Path, content: str) -> None:
    """Write UTF-8 text without creating directories and without leaving a partial file."""
    temp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
        os.replace(temp, path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


@guarded
def report(
    bug_id: Annotated[int, typer.Argument(help="Id of the bug.")],
    format: Annotated[ReportFormat, typer.Option("--format", help="Report format.")] = (
        ReportFormat.MD
    ),
    output: Annotated[
        Path | None, typer.Option("--output", help="Write the report to this file.")
    ] = None,
) -> None:
    context = bootstrap()
    try:
        with session_factory(context.engine)() as session:
            result = get_report(session, bug_id, format)
            if result.rendered:
                session.commit()
    finally:
        context.close()
    if output is None:
        typer.echo(result.content, nl=False)
        return
    try:
        _write_file(output, result.content)
    except OSError as exc:
        raise fail(f"Cannot write report to {output}: {exc.strerror or exc}") from None
    echo(f"Report written to {output}")


def register(app: typer.Typer) -> None:
    app.command("report", help="Print or save the report of a processed bug.")(report)
