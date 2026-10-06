"""Report data: one structured object built from stored rows only."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from bugflow.db.models import (
    Bug,
    BugReport,
    ComponentClassification,
    ResolutionPlan,
    SeverityClassification,
    TechnicalAnalysis,
)
from bugflow.enums import (
    Component,
    Environment,
    Priority,
    ResolutionStatus,
    Seniority,
    Severity,
    Team,
)
from bugflow.services.errors import NotFoundError


class SimilarBug(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str | None


class ReportData(BaseModel):
    """Everything a report states, in typed form. Enums are members; labels come later."""

    model_config = ConfigDict(frozen=True)

    bug_id: int
    title: str
    description: str
    reproduction_steps: str
    system_version: str
    environment: Environment
    reporting_team: Team
    opened_at: datetime
    component: Component
    component_justification: str
    severity: Severity
    severity_justification: str
    user_impact: str
    root_cause: str
    technical_impact: str
    debugging_approach: tuple[str, ...]
    proposed_solution: str
    side_effects: tuple[str, ...]
    similar_bugs: tuple[SimilarBug, ...]
    resolution_status: ResolutionStatus
    assigned_team: Team
    assignee_role: str
    assignee_seniority: Seniority
    assignee_skills: tuple[str, ...]
    target_days: int
    priority: Priority
    notes: str
    executive_summary: str
    key_takeaways: tuple[str, ...]
    next_steps: tuple[str, ...]
    completed_on: date
    deadline: date


def _not_found(bug_id: int) -> NotFoundError:
    return NotFoundError(f"Bug {bug_id} not found")


def _no_report(bug_id: int) -> NotFoundError:
    return NotFoundError(f"Bug {bug_id} has no report; triage it first")


def load_report_data(session: Session, bug_id: int) -> ReportData:
    """Read the stored rows of one bug through the session; no LLM, no network."""
    bug = session.get(Bug, bug_id)
    if bug is None:
        raise _not_found(bug_id)
    component = session.get(ComponentClassification, bug_id)
    severity = session.get(SeverityClassification, bug_id)
    analysis = session.get(TechnicalAnalysis, bug_id)
    plan = session.get(ResolutionPlan, bug_id)
    report = session.get(BugReport, bug_id)
    if component is None or severity is None or analysis is None or plan is None or report is None:
        raise _no_report(bug_id)
    referenced = [int(item) for item in analysis.referenced_similar_bug_ids]
    titles: dict[int, str] = {}
    if referenced:
        titles = dict(
            session.execute(select(Bug.id, Bug.title).where(Bug.id.in_(referenced))).tuples().all()
        )
    completed_on = report.created_at.astimezone(UTC).date()
    profile = plan.assignee_profile
    return ReportData(
        bug_id=bug.id,
        title=bug.title,
        description=bug.description,
        reproduction_steps=bug.reproduction_steps,
        system_version=bug.system_version,
        environment=Environment(bug.environment),
        reporting_team=Team(bug.reporting_team),
        opened_at=bug.opened_at,
        component=Component(component.component),
        component_justification=component.justification,
        severity=Severity(severity.severity),
        severity_justification=severity.justification,
        user_impact=severity.user_impact,
        root_cause=analysis.root_cause,
        technical_impact=analysis.technical_impact,
        debugging_approach=tuple(analysis.debugging_approach),
        proposed_solution=analysis.proposed_solution,
        side_effects=tuple(analysis.side_effects),
        similar_bugs=tuple(SimilarBug(id=item, title=titles.get(item)) for item in referenced),
        resolution_status=ResolutionStatus(plan.resolution_status),
        assigned_team=Team(plan.assigned_team),
        assignee_role=profile["role"],
        assignee_seniority=Seniority(profile["seniority"]),
        assignee_skills=tuple(profile["skills"]),
        target_days=plan.target_days,
        priority=Priority(plan.priority),
        notes=plan.notes,
        executive_summary=report.executive_summary,
        key_takeaways=tuple(report.key_takeaways),
        next_steps=tuple(report.next_steps),
        completed_on=completed_on,
        deadline=completed_on + timedelta(days=plan.target_days),
    )
