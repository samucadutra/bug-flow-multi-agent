"""Small helpers shared by integration tests."""

from __future__ import annotations

from sqlalchemy import Engine, text

from bugflow.db.engine import session_factory
from bugflow.db.models import (
    Bug,
    BugEmbedding,
    BugReport,
    ComponentClassification,
    ResolutionPlan,
    Run,
    RunLog,
    RunStep,
    SeverityClassification,
    TechnicalAnalysis,
)


def add_numbered(engine: Engine, count: int) -> list[int]:
    """Bugs titled "Batchbug 01" ... with valid values for every column."""
    with session_factory(engine)() as db_session:
        bugs = [
            Bug(
                title=f"Batchbug {number:02d}",
                description=f"Description of batch bug {number}.",
                reproduction_steps="1. Open the page.",
                system_version="web 1.0.0",
                environment="testing",
                reporting_team="qa",
            )
            for number in range(1, count + 1)
        ]
        db_session.add_all(bugs)
        db_session.commit()
        return [bug.id for bug in bugs]


OPEN_BUG_FIELDS = {
    "title": "Checkout button does nothing on Safari 17",
    "description": "Clicking Place order shows no response and no network call.",
    "reproduction_steps": "Add an item, go to checkout in Safari 17, click the button.",
    "system_version": "web 3.8.2",
    "environment": "production",
    "reporting_team": "support",
}
RESULT_TABLES = (
    "component_classifications",
    "severity_classifications",
    "technical_analyses",
    "resolution_plans",
    "bug_reports",
)


def add_bug(engine: Engine, status: str = "open", **overrides: str) -> int:
    fields = {**OPEN_BUG_FIELDS, **overrides}
    with session_factory(engine)() as db_session:
        bug = Bug(status=status, **fields)
        db_session.add(bug)
        db_session.commit()
        return bug.id


def result_row_counts(engine: Engine, bug_id: int) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE bug_id = :id"),  # noqa: S608
                {"id": bug_id},
            ).scalar_one()
            for table in RESULT_TABLES
        }


def stored_status(engine: Engine, bug_id: int) -> str:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT status FROM bugs WHERE id = :id"), {"id": bug_id}
        ).scalar_one()


def wait_until(predicate, timeout: float = 30.0, interval: float = 0.05):
    """Poll `predicate` until it returns something truthy; fail the test on timeout."""
    import time

    deadline = time.monotonic() + timeout
    while True:
        value = predicate()
        if value:
            return value
        if time.monotonic() >= deadline:
            raise AssertionError("condition not met before the timeout")
        time.sleep(interval)


def run_row(engine: Engine, run_id: int):
    with engine.connect() as connection:
        return connection.execute(text("SELECT * FROM runs WHERE id = :id"), {"id": run_id}).one()


def run_rows(engine: Engine, where: str = "true"):
    with engine.connect() as connection:
        return connection.execute(
            text(f"SELECT * FROM runs WHERE {where} ORDER BY id")  # noqa: S608
        ).all()


def step_rows(engine: Engine, run_id: int):
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT * FROM run_steps WHERE run_id = :id ORDER BY position"), {"id": run_id}
        ).all()


def log_rows(engine: Engine, run_id: int):
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT * FROM run_logs WHERE run_id = :id ORDER BY id"), {"id": run_id}
        ).all()


def is_final(engine: Engine, run_id: int) -> bool:
    return run_row(engine, run_id).status in ("succeeded", "failed")


def wait_final(engine: Engine, run_id: int, timeout: float = 60.0):
    wait_until(lambda: is_final(engine, run_id), timeout)
    return run_row(engine, run_id)


AGENT_KEYS = (
    "component_classifier",
    "severity_classifier",
    "technical_analyst",
    "resolution_manager",
    "bug_documenter",
)


def _add_results(db_session, bug_id: int, run_id: int) -> None:
    db_session.add_all(
        [
            ComponentClassification(
                bug_id=bug_id, run_id=run_id, component="frontend", justification="Safari bug"
            ),
            SeverityClassification(
                bug_id=bug_id,
                run_id=run_id,
                severity="major",
                justification="Blocks checkout",
                user_impact="Users cannot pay",
            ),
            TechnicalAnalysis(
                bug_id=bug_id,
                run_id=run_id,
                root_cause="Event handler missing",
                technical_impact="Checkout blocked",
                debugging_approach=["Reproduce"],
                proposed_solution="Fix the handler",
                side_effects=[],
                referenced_similar_bug_ids=[],
            ),
            ResolutionPlan(
                bug_id=bug_id,
                run_id=run_id,
                resolution_status="planned",
                assigned_team="frontend",
                assignee_profile={"role": "engineer"},
                target_days=3,
                priority="high",
                notes="",
            ),
            BugReport(
                bug_id=bug_id,
                run_id=run_id,
                executive_summary="Checkout fails on Safari",
                key_takeaways=["One"],
                next_steps=["Fix"],
                markdown="# Report",
                html="<h1>Report</h1>",
            ),
        ]
    )


def add_bug_with_history(engine: Engine, kind: str, **overrides: str) -> int:
    """A bug in the state of an F08 handle: processed, failed, processing or open (no history)."""
    status = kind if kind in ("processed", "failed", "processing") else "open"
    bug_id = add_bug(engine, status=status, **overrides)
    if kind == "open":
        return bug_id
    with session_factory(engine)() as db_session:
        run_status = {"processed": "succeeded", "failed": "failed", "processing": "running"}[kind]
        run = Run(
            type="triage",
            bug_id=bug_id,
            status=run_status,
            progress_done=5 if kind == "processed" else 0,
            progress_total=5,
            error="earlier failure" if kind == "failed" else None,
        )
        db_session.add(run)
        db_session.flush()
        step_states = {
            "processed": ["succeeded"] * 5,
            "failed": ["succeeded", "succeeded", "failed", "skipped", "skipped"],
            "processing": ["running", "pending", "pending", "pending", "pending"],
        }[kind]
        for position, (key, state) in enumerate(zip(AGENT_KEYS, step_states, strict=True), 1):
            db_session.add(
                RunStep(
                    run_id=run.id,
                    position=position,
                    agent_key=key,
                    status=state,
                    input={"position": position},
                    output={"ok": True} if state == "succeeded" else None,
                    error="step failed" if state == "failed" else None,
                )
            )
        for number in range(1 if kind == "processing" else 3):
            db_session.add(RunLog(run_id=run.id, level="info", message=f"log line {number}"))
        if kind != "processing":
            db_session.add(BugEmbedding(bug_id=bug_id, embedding=[0.1] * 1536, text_hash="a" * 64))
        if kind == "processed":
            _add_results(db_session, bug_id, run.id)
        db_session.commit()
    return bug_id


def kept_snapshot(engine: Engine, bug_id: int | None = None) -> dict[str, list[tuple]]:
    """Every row of the tables reopen must keep (all bugs, or one bug's rows)."""
    queries = {
        "runs": ("SELECT * FROM runs {w} ORDER BY id", "WHERE bug_id = :id"),
        "run_steps": (
            "SELECT * FROM run_steps {w} ORDER BY id",
            "WHERE run_id IN (SELECT id FROM runs WHERE bug_id = :id)",
        ),
        "run_logs": (
            "SELECT * FROM run_logs {w} ORDER BY id",
            "WHERE run_id IN (SELECT id FROM runs WHERE bug_id = :id)",
        ),
        "bug_embeddings": (
            "SELECT bug_id, text_hash, embedded_at FROM bug_embeddings {w} ORDER BY 1",
            "WHERE bug_id = :id",
        ),
    }
    with engine.connect() as connection:
        return {
            name: [
                tuple(row)
                for row in connection.execute(
                    text(query.format(w="" if bug_id is None else clause)), {"id": bug_id}
                )
            ]
            for name, (query, clause) in queries.items()
        }


def bug_row(engine: Engine, bug_id: int) -> tuple:
    with engine.connect() as connection:
        return tuple(
            connection.execute(text("SELECT * FROM bugs WHERE id = :id"), {"id": bug_id}).one()
        )


def result_rows(engine: Engine, bug_id: int) -> dict[str, list[tuple]]:
    with engine.connect() as connection:
        return {
            table: [
                tuple(row)
                for row in connection.execute(
                    text(f"SELECT * FROM {table} WHERE bug_id = :id"),  # noqa: S608
                    {"id": bug_id},
                )
            ]
            for table in RESULT_TABLES
        }
