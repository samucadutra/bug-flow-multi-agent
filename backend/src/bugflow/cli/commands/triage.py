"""`bugflow triage`: run the five triage agents on one bug or on every open bug."""

from __future__ import annotations

import typer

from bugflow.cli.context import bootstrap
from bugflow.cli.output import echo, fail, guarded
from bugflow.services.triage import StepSummary, TriageOutcome, triage_all, triage_bug

USAGE_ERROR = "Specify exactly one of --bug or --all"


def _print_step(step: StepSummary) -> None:
    if step.succeeded:
        echo(f"{step.label}: {step.summary}")


def _result_line(outcome: TriageOutcome) -> str:
    if outcome.processed:
        return f"Bug {outcome.bug_id} processed"
    return f"Bug {outcome.bug_id} failed: {outcome.error}"


@guarded
def triage(
    bug: int | None = typer.Option(None, "--bug", help="Id of the bug to triage."),
    all_bugs: bool = typer.Option(False, "--all", help="Triage every open bug, one at a time."),
) -> None:
    if (bug is None) == (not all_bugs):
        raise fail(USAGE_ERROR, 2)
    context = bootstrap()
    similar_k = context.settings.similar_bugs_k
    try:
        if bug is not None:
            outcomes = [
                triage_bug(
                    context.engine,
                    context.get_client,
                    bug,
                    context.redactor,
                    _print_step,
                    similar_k=similar_k,
                )
            ]
            echo(_result_line(outcomes[0]))
        else:
            outcomes = triage_all(
                context.engine,
                context.get_client,
                context.redactor,
                _print_step,
                on_outcome=lambda outcome: echo(_result_line(outcome)),
                similar_k=similar_k,
            )
    finally:
        context.close()
    failed = sum(1 for outcome in outcomes if not outcome.processed)
    if bug is None:
        if not outcomes:
            echo("No open bugs to triage")
        else:
            processed = len(outcomes) - failed
            echo(f"Triaged {len(outcomes)} bugs: {processed} processed, {failed} failed")
    if failed:
        raise typer.Exit(1)


def register(app: typer.Typer) -> None:
    app.command(
        "triage", help="Run the triage agents on one bug (--bug) or all open bugs (--all)."
    )(triage)
