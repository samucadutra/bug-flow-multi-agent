"""Builders and parsers shared by the F09 API tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Engine

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
from bugflow.services.embeddings import index_all_bugs
from tests_helpers import AGENT_KEYS, OPEN_BUG_FIELDS, add_bug

PROCESSED_TITLE = "Processed checkout bug"
PROCESSED_MARKDOWN = f"# {PROCESSED_TITLE}\n\nStored report body.\n"
PROCESSED_HTML = f"<h1>{PROCESSED_TITLE}</h1><p>Stored report body.</p>"
BASE = "/api/v1"


def add_processed_bug(engine: Engine) -> dict[str, int]:
    """Handle `processed-bug` with `processed-run`, five steps, four logs and five result rows."""
    bug_id = add_bug(engine, status="processed", title=PROCESSED_TITLE)
    with session_factory(engine)() as session:
        run = Run(
            type="triage",
            bug_id=bug_id,
            status="succeeded",
            progress_done=5,
            progress_total=5,
            started_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
            finished_at=datetime(2026, 10, 2, 10, 1, tzinfo=UTC),
        )
        session.add(run)
        session.flush()
        for position, key in enumerate(AGENT_KEYS, start=1):
            session.add(
                RunStep(
                    run_id=run.id,
                    position=position,
                    agent_key=key,
                    status="succeeded",
                    input={"position": position},
                    output={"ok": True},
                    duration_ms=100 * position,
                )
            )
        session.flush()
        for number in range(1, 5):
            session.add(RunLog(run_id=run.id, level="INFO", message=f"log line {number}"))
        session.flush()
        session.add_all(
            [
                ComponentClassification(
                    bug_id=bug_id, run_id=run.id, component="frontend", justification="Safari"
                ),
                SeverityClassification(
                    bug_id=bug_id,
                    run_id=run.id,
                    severity="major",
                    justification="Blocks checkout",
                    user_impact="Users cannot pay",
                ),
                TechnicalAnalysis(
                    bug_id=bug_id,
                    run_id=run.id,
                    root_cause="Handler missing",
                    technical_impact="Checkout blocked",
                    debugging_approach=["Reproduce"],
                    proposed_solution="Fix the handler",
                    side_effects=[],
                    referenced_similar_bug_ids=[],
                ),
                ResolutionPlan(
                    bug_id=bug_id,
                    run_id=run.id,
                    resolution_status="planned",
                    assigned_team="frontend",
                    assignee_profile={"role": "engineer", "seniority": "senior", "skills": ["js"]},
                    target_days=5,
                    priority="high",
                    notes="",
                ),
                BugReport(
                    bug_id=bug_id,
                    run_id=run.id,
                    executive_summary="Checkout fails on Safari",
                    key_takeaways=["One"],
                    next_steps=["Fix"],
                    markdown=PROCESSED_MARKDOWN,
                    html=PROCESSED_HTML,
                ),
                BugEmbedding(bug_id=bug_id, embedding=[0.1] * 1536, text_hash="a" * 64),
            ]
        )
        session.commit()
        return {"bug_id": bug_id, "run_id": run.id}


def add_seed_run(engine: Engine) -> int:
    """Handle `seed-run`: a succeeded seed run older than `processed-run`."""
    with session_factory(engine)() as session:
        run = Run(
            type="seed",
            status="succeeded",
            progress_done=20,
            progress_total=20,
            started_at=datetime(2026, 10, 1, 9, 0, tzinfo=UTC),
            finished_at=datetime(2026, 10, 1, 9, 0, 5, tzinfo=UTC),
        )
        session.add(run)
        session.flush()
        session.add(RunLog(run_id=run.id, level="INFO", message="Seeded 20 bugs"))
        session.commit()
        return run.id


def index_everything(engine: Engine, client: Any) -> None:
    index_all_bugs(session_factory(engine), client)


def bug_count(engine: Engine) -> int:
    with session_factory(engine)() as session:
        return session.query(Bug).count()


def parse_sse(text: str) -> list[dict[str, Any]]:
    """Frames of an event stream as `{id, event, data}` with `data` decoded from JSON."""
    frames: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        frame: dict[str, Any] = {}
        for line in block.split("\n"):
            name, _, value = line.partition(": ")
            frame[name] = json.loads(value) if name == "data" else value
        frames.append(frame)
    return frames


def create_body(**overrides: str) -> dict[str, str]:
    return {**OPEN_BUG_FIELDS, **overrides}
