"""Report services: render and store the Markdown and HTML report, read it back, and the hook.

Services take a session, flush and never commit. The F05 result hook runs inside the final
triage transaction, after the five result rows are inserted and before the bug is `processed`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from bugflow.db.models import Bug, BugReport
from bugflow.reports.data import ReportData, load_report_data
from bugflow.reports.render import render_html, render_markdown
from bugflow.services.errors import NotFoundError, ServiceError
from bugflow.services.triage import (
    TriageResults,
    register_result_hook,
    unregister_result_hook,
)

Renderer = Callable[[ReportData], tuple[str, str]]


class ReportFormat(StrEnum):
    MD = "md"
    HTML = "html"


class RenderedReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    bug_id: int
    markdown: str
    html: str
    completed_on: date
    deadline: date


class ReportRead(BaseModel):
    """The stored text of one format. `rendered` is true when this call had to render it."""

    model_config = ConfigDict(frozen=True)

    bug_id: int
    format: ReportFormat
    content: str
    rendered: bool = False


class ReportRenderError(ServiceError):
    """Rendering failed; the message is `Report rendering failed: <first line of the cause>`."""


def default_renderer(data: ReportData) -> tuple[str, str]:
    return render_markdown(data), render_html(data)


_renderer: Renderer = default_renderer


def _report_row(session: Session, bug_id: int) -> BugReport:
    if session.get(Bug, bug_id) is None:
        raise NotFoundError(f"Bug {bug_id} not found")
    row = session.get(BugReport, bug_id)
    if row is None:
        raise NotFoundError(f"Bug {bug_id} has no report; triage it first")
    return row


def _render_and_store(session: Session, bug_id: int, renderer: Renderer) -> RenderedReport:
    data = load_report_data(session, bug_id)
    try:
        markdown, html = renderer(data)
    except Exception as exc:
        cause = (str(exc) or type(exc).__name__).splitlines() or [type(exc).__name__]
        raise ReportRenderError(f"Report rendering failed: {cause[0]}") from None
    row = _report_row(session, bug_id)
    row.markdown = markdown
    row.html = html
    session.flush()
    return RenderedReport(
        bug_id=bug_id,
        markdown=markdown,
        html=html,
        completed_on=data.completed_on,
        deadline=data.deadline,
    )


def render_report(session: Session, bug_id: int) -> RenderedReport:
    """Render both formats from the stored rows and store them on `bug_reports`; no commit."""
    return _render_and_store(session, bug_id, _renderer)


def get_report(session: Session, bug_id: int, format: ReportFormat) -> ReportRead:
    """The stored text of the format; renders and stores first when it is missing."""
    row = _report_row(session, bug_id)
    stored = row.markdown if format == ReportFormat.MD else row.html
    if stored is not None:
        return ReportRead(bug_id=bug_id, format=format, content=stored)
    rendered = render_report(session, bug_id)
    content = rendered.markdown if format == ReportFormat.MD else rendered.html
    return ReportRead(bug_id=bug_id, format=format, content=content, rendered=True)


def report_result_hook(session: Session, bug_id: int, results: TriageResults) -> None:
    """F05 result hook: renders from the stored rows (the agent results are not used)."""
    _render_and_store(session, bug_id, _renderer)


def install_report_hook(render: Renderer | None = None) -> None:
    """Register `report_result_hook` once; `render` replaces the renderer (test mechanism)."""
    global _renderer
    _renderer = render if render is not None else default_renderer
    unregister_result_hook(report_result_hook)
    register_result_hook(report_result_hook)
