"""Dashboard counts: bugs by status, by component and by severity (zero-filled)."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bugflow.db.models import Bug, ComponentClassification, SeverityClassification
from bugflow.enums import BugStatus, Component, Severity, codes


class DashboardStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    total: int
    by_status: dict[str, int]
    by_component: dict[str, int]
    by_severity: dict[str, int]


def zero_filled(enum_cls: type[StrEnum], rows: Iterable[tuple[str, int]]) -> dict[str, int]:
    """One entry per code of the enum in canonical order; codes without rows count 0."""
    counts = {code: 0 for code in codes(enum_cls)}
    for code, count in rows:
        if code in counts:
            counts[code] = int(count)
    return counts


def assemble_stats(
    status_rows: Iterable[tuple[str, int]],
    component_rows: Iterable[tuple[str, int]],
    severity_rows: Iterable[tuple[str, int]],
) -> DashboardStats:
    by_status = zero_filled(BugStatus, status_rows)
    return DashboardStats(
        total=sum(by_status.values()),
        by_status=by_status,
        by_component=zero_filled(Component, component_rows),
        by_severity=zero_filled(Severity, severity_rows),
    )


def _grouped(session: Session, column) -> list[tuple[str, int]]:
    statement = select(column, func.count()).group_by(column)
    return [(str(value), int(count)) for value, count in session.execute(statement)]


def dashboard_stats(session: Session) -> DashboardStats:
    """Read-only counts using `GROUP BY` on the stored columns."""
    return assemble_stats(
        _grouped(session, Bug.status),
        _grouped(session, ComponentClassification.component),
        _grouped(session, SeverityClassification.severity),
    )
