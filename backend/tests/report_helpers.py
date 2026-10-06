"""Helpers for the report tests: plain `ReportData` and processed-bug states in the database."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import Engine

from bugflow.db.engine import session_factory
from bugflow.db.models import (
    Bug,
    BugReport,
    ComponentClassification,
    ResolutionPlan,
    Run,
    SeverityClassification,
    TechnicalAnalysis,
)
from bugflow.reports.data import ReportData, SimilarBug

REPORT_BUG_FIELDS: dict[str, Any] = {
    "title": "Checkout button does nothing on Safari 17",
    "description": "Clicking Place order shows no response and no network call.",
    "reproduction_steps": "Add an item, go to checkout in Safari 17, click the button.",
    "system_version": "web 3.8.2",
    "environment": "production",
    "reporting_team": "support",
    "status": "processed",
    "opened_at": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
}
EXECUTIVE_SUMMARY = "Clicking Place order does nothing on Safari 17 and no request is sent."
COMPLETED_AT = datetime(2026, 3, 30, 23, 30, tzinfo=UTC)

HOSTILE_OVERRIDES: dict[str, Any] = {
    "title": 'Crash on `save` | <b>bold</b> says "no"',
    "description": (
        "Saving a <script>alert(1)</script> note fails.\n"
        "Fence test: ``` and `inline` and a | pipe.\n"
        "Quote \"double\" and 'single' & ampersand."
    ),
    "reproduction_steps": ("1. Type `<img src=x onerror=alert(1)>` in the note.\n2. Press | Save."),
    "component_justification": "Looks like a `null` check | missing.",
    "resolution_status": "planned",
    "assignee_role": "Backend | Platform engineer",
    "assignee_skills": ["Python", "SQL | NoSQL"],
    "notes": "Check `retry|backoff` and <config>.",
    "executive_summary": "Save fails on <b>special</b> input.",
}


def sample_report_data(**overrides: Any) -> ReportData:
    """Plain `ReportData` equal to the contract's `report-bug` state."""
    values: dict[str, Any] = {
        "bug_id": 3,
        "title": REPORT_BUG_FIELDS["title"],
        "description": REPORT_BUG_FIELDS["description"],
        "reproduction_steps": REPORT_BUG_FIELDS["reproduction_steps"],
        "system_version": "web 3.8.2",
        "environment": "production",
        "reporting_team": "support",
        "opened_at": datetime(2026, 3, 1, 10, 0, tzinfo=UTC),
        "component": "backend",
        "component_justification": "The failing logic runs on the server.",
        "severity": "major",
        "severity_justification": "Checkout is degraded for many users.",
        "user_impact": "Customers cannot complete orders on Safari.",
        "root_cause": "A Safari-specific request handler error.",
        "technical_impact": "Orders fail silently.",
        "debugging_approach": ("Reproduce on Safari 17", "Inspect the server logs"),
        "proposed_solution": "Fix the handler and add a regression test.",
        "side_effects": (),
        "similar_bugs": (SimilarBug(id=2, title="Payment form freezes on Safari 17"),),
        "resolution_status": "needs_info",
        "assigned_team": "backend",
        "assignee_role": "Backend engineer",
        "assignee_seniority": "senior",
        "assignee_skills": ("Python", "PostgreSQL"),
        "target_days": 5,
        "priority": "high",
        "notes": "Waiting for browser logs.",
        "executive_summary": EXECUTIVE_SUMMARY,
        "key_takeaways": ("Only Safari 17 is affected.", "No network call is made."),
        "next_steps": ("Collect browser logs.", "Reproduce on a test device."),
        "completed_on": date(2026, 3, 30),
        "deadline": date(2026, 4, 4),
    }
    values.update(overrides)
    return ReportData.model_validate(values)


def add_processed_bug(
    engine: Engine,
    *,
    similar_ids: list[int] | None = None,
    stored_markdown: str | None = None,
    stored_html: str | None = None,
    bug: dict[str, Any] | None = None,
    **overrides: Any,
) -> int:
    """INSERT a processed bug with one succeeded triage run and one row per result table.

    `overrides` use the `ReportData` field names of the result values (component, severity,
    resolution_status, assigned_team, target_days, notes, ...).
    """
    values: dict[str, Any] = {
        "component": "backend",
        "component_justification": "The failing logic runs on the server.",
        "severity": "major",
        "severity_justification": "Checkout is degraded for many users.",
        "user_impact": "Customers cannot complete orders on Safari.",
        "root_cause": "A Safari-specific request handler error.",
        "technical_impact": "Orders fail silently.",
        "debugging_approach": ["Reproduce on Safari 17", "Inspect the server logs"],
        "proposed_solution": "Fix the handler and add a regression test.",
        "side_effects": [],
        "resolution_status": "needs_info",
        "assigned_team": "backend",
        "assignee_role": "Backend engineer",
        "assignee_seniority": "senior",
        "assignee_skills": ["Python", "PostgreSQL"],
        "target_days": 5,
        "priority": "high",
        "notes": "Waiting for browser logs.",
        "executive_summary": EXECUTIVE_SUMMARY,
        "key_takeaways": ["Only Safari 17 is affected.", "No network call is made."],
        "next_steps": ["Collect browser logs.", "Reproduce on a test device."],
    }
    bug_fields = {**REPORT_BUG_FIELDS, **(bug or {})}
    for key in ("title", "description", "reproduction_steps"):
        if key in overrides:
            bug_fields[key] = overrides.pop(key)
    values.update(overrides)
    with session_factory(engine)() as db_session:
        row = Bug(**bug_fields)
        db_session.add(row)
        run = Run(type="triage", status="succeeded", bug_id=None)
        db_session.add(run)
        db_session.flush()
        run.bug_id = row.id
        key = {"bug_id": row.id, "run_id": run.id}
        db_session.add_all(
            [
                ComponentClassification(
                    **key,
                    component=values["component"],
                    justification=values["component_justification"],
                ),
                SeverityClassification(
                    **key,
                    severity=values["severity"],
                    justification=values["severity_justification"],
                    user_impact=values["user_impact"],
                ),
                TechnicalAnalysis(
                    **key,
                    root_cause=values["root_cause"],
                    technical_impact=values["technical_impact"],
                    debugging_approach=values["debugging_approach"],
                    proposed_solution=values["proposed_solution"],
                    side_effects=values["side_effects"],
                    referenced_similar_bug_ids=similar_ids or [],
                ),
                ResolutionPlan(
                    **key,
                    resolution_status=values["resolution_status"],
                    assigned_team=values["assigned_team"],
                    assignee_profile={
                        "role": values["assignee_role"],
                        "seniority": values["assignee_seniority"],
                        "skills": values["assignee_skills"],
                    },
                    target_days=values["target_days"],
                    priority=values["priority"],
                    notes=values["notes"],
                ),
                BugReport(
                    **key,
                    executive_summary=values["executive_summary"],
                    key_takeaways=values["key_takeaways"],
                    next_steps=values["next_steps"],
                    markdown=stored_markdown,
                    html=stored_html,
                    created_at=COMPLETED_AT,
                ),
            ]
        )
        db_session.commit()
        return row.id
