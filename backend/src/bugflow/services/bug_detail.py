"""Bug detail: the bug fields, its stored triage results and its latest run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from bugflow.db.models import (
    BugReport,
    ComponentClassification,
    ResolutionPlan,
    Run,
    SeverityClassification,
    TechnicalAnalysis,
)
from bugflow.enums import Component, Priority, ResolutionStatus, Severity, Team
from bugflow.services.bugs import get_bug
from bugflow.services.schemas import BugRead, RunRead


class ComponentResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    component: Component
    justification: str


class SeverityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    severity: Severity
    justification: str
    user_impact: str


class AnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    root_cause: str
    technical_impact: str
    debugging_approach: list[str]
    proposed_solution: str
    side_effects: list[str]
    referenced_similar_bug_ids: list[int]


class PlanResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    resolution_status: ResolutionStatus
    assigned_team: Team
    assignee_profile: dict[str, Any]
    target_days: int
    priority: Priority
    notes: str


class ReportSummary(BaseModel):
    """The report fields without the rendered bodies (those come from the report endpoint)."""

    model_config = ConfigDict(frozen=True)

    executive_summary: str
    key_takeaways: list[str]
    next_steps: list[str]
    has_markdown: bool
    has_html: bool


class BugResults(BaseModel):
    model_config = ConfigDict(frozen=True)

    component: ComponentResult | None = None
    severity: SeverityResult | None = None
    analysis: AnalysisResult | None = None
    plan: PlanResult | None = None
    report: ReportSummary | None = None


class BugDetail(BugRead):
    results: BugResults
    latest_run: RunRead | None = None


def get_bug_detail(session: Session, bug_id: int) -> BugDetail:
    """The bug with its stored results (null when absent) and its most recent run."""
    bug = get_bug(session, bug_id)
    component = session.get(ComponentClassification, bug_id)
    severity = session.get(SeverityClassification, bug_id)
    analysis = session.get(TechnicalAnalysis, bug_id)
    plan = session.get(ResolutionPlan, bug_id)
    report = session.get(BugReport, bug_id)
    latest = session.scalars(
        select(Run).where(Run.bug_id == bug_id).order_by(Run.started_at.desc(), Run.id.desc())
    ).first()
    results = BugResults(
        component=(
            ComponentResult.model_validate(component, from_attributes=True) if component else None
        ),
        severity=(
            SeverityResult.model_validate(severity, from_attributes=True) if severity else None
        ),
        analysis=(
            AnalysisResult.model_validate(analysis, from_attributes=True) if analysis else None
        ),
        plan=PlanResult.model_validate(plan, from_attributes=True) if plan else None,
        report=(
            ReportSummary(
                executive_summary=report.executive_summary,
                key_takeaways=report.key_takeaways,
                next_steps=report.next_steps,
                has_markdown=bool(report.markdown),
                has_html=bool(report.html),
            )
            if report
            else None
        ),
    )
    return BugDetail(
        **bug.model_dump(),
        results=results,
        latest_run=RunRead.model_validate(latest, from_attributes=True) if latest else None,
    )
