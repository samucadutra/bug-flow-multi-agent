"""Bug services: create, get, update while open, list, and the status transition rule.

Every function flushes and never commits; the caller owns the transaction.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, Select, case, func, select, update
from sqlalchemy.orm import Session

from bugflow.db.models import Bug, ComponentClassification, SeverityClassification
from bugflow.enums import BugStatus, Severity
from bugflow.services.errors import NotFoundError, StateConflictError
from bugflow.services.schemas import (
    BugCreate,
    BugListQuery,
    BugPage,
    BugRead,
    BugUpdate,
    SortBy,
    SortDir,
)

ALLOWED_TRANSITIONS: dict[BugStatus, frozenset[BugStatus]] = {
    BugStatus.OPEN: frozenset({BugStatus.PROCESSING}),
    BugStatus.PROCESSING: frozenset({BugStatus.PROCESSED, BugStatus.FAILED}),
    BugStatus.PROCESSED: frozenset({BugStatus.OPEN}),
    BugStatus.FAILED: frozenset({BugStatus.OPEN}),
}

_ESCAPE = "\\"


def ensure_transition_allowed(current: BugStatus, new: BugStatus) -> None:
    """Raise `StateConflictError` unless the status change is in `ALLOWED_TRANSITIONS`."""
    if new not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise StateConflictError(
            f"Status change from '{current.value}' to '{new.value}' is not allowed"
        )


def _not_found(bug_id: int) -> NotFoundError:
    return NotFoundError(f"Bug {bug_id} not found")


def _read_query() -> Select[Any]:
    """Bug columns plus the classification values (null before triage)."""
    return (
        select(
            Bug.id,
            Bug.title,
            Bug.description,
            Bug.reproduction_steps,
            Bug.system_version,
            Bug.environment,
            Bug.reporting_team,
            Bug.status,
            Bug.opened_at,
            Bug.updated_at,
            ComponentClassification.component,
            SeverityClassification.severity,
        )
        .select_from(Bug)
        .outerjoin(ComponentClassification, ComponentClassification.bug_id == Bug.id)
        .outerjoin(SeverityClassification, SeverityClassification.bug_id == Bug.id)
    )


def create_bug(session: Session, data: BugCreate) -> BugRead:
    """Insert a bug with status `open` and flush."""
    bug = Bug(
        title=data.title,
        description=data.description,
        reproduction_steps=data.reproduction_steps,
        system_version=data.system_version,
        environment=data.environment.value,
        reporting_team=data.reporting_team.value,
        status=BugStatus.OPEN.value,
    )
    session.add(bug)
    session.flush()
    return get_bug(session, bug.id)


def get_bug(session: Session, bug_id: int) -> BugRead:
    row = session.execute(_read_query().where(Bug.id == bug_id)).mappings().first()
    if row is None:
        raise _not_found(bug_id)
    return BugRead.model_validate(dict(row))


def update_bug(session: Session, bug_id: int, data: BugUpdate) -> BugRead:
    """Edit the provided fields while the bug is `open`, atomically."""
    statement = (
        update(Bug)
        .where(Bug.id == bug_id, Bug.status == BugStatus.OPEN.value)
        .values(**data.changes(), updated_at=func.clock_timestamp())
        .execution_options(synchronize_session=False)
    )
    if session.execute(statement).rowcount == 0:
        exists = session.execute(select(Bug.id).where(Bug.id == bug_id)).first()
        if exists is None:
            raise _not_found(bug_id)
        raise StateConflictError(f"Bug {bug_id} is not open and cannot be edited")
    return get_bug(session, bug_id)


def _escape_like(text: str) -> str:
    return (
        text.replace(_ESCAPE, _ESCAPE * 2).replace("%", f"{_ESCAPE}%").replace("_", f"{_ESCAPE}_")
    )


def _filters(query: BugListQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if query.status is not None:
        conditions.append(Bug.status == query.status.value)
    if query.component is not None:
        conditions.append(ComponentClassification.component == query.component.value)
    if query.severity is not None:
        conditions.append(SeverityClassification.severity == query.severity.value)
    if query.environment is not None:
        conditions.append(Bug.environment == query.environment.value)
    if query.reporting_team is not None:
        conditions.append(Bug.reporting_team == query.reporting_team.value)
    if query.search is not None:
        pattern = f"%{_escape_like(query.search)}%"
        conditions.append(
            Bug.title.ilike(pattern, escape=_ESCAPE)
            | Bug.description.ilike(pattern, escape=_ESCAPE)
        )
    return conditions


def _rank(column: Any, order: list[Any]) -> ColumnElement[int]:
    return case({member.value: index for index, member in enumerate(order)}, value=column, else_=99)


def _ordering(query: BugListQuery) -> list[ColumnElement[Any]]:
    descending = query.sort_dir is SortDir.DESC

    def direct(expression: Any) -> ColumnElement[Any]:
        return expression.desc() if descending else expression.asc()

    if query.sort_by is SortBy.OPENED_AT:
        return [direct(Bug.opened_at), direct(Bug.id)]
    tie_break = [Bug.opened_at.desc(), Bug.id.desc()]
    if query.sort_by is SortBy.STATUS:
        return [direct(_rank(Bug.status, list(BugStatus))), *tie_break]
    untriaged_last = case((SeverityClassification.severity.is_(None), 1), else_=0)
    return [
        untriaged_last.asc(),
        direct(_rank(SeverityClassification.severity, list(Severity))),
        *tie_break,
    ]


def list_bugs(session: Session, query: BugListQuery) -> BugPage:
    """Filter, search, sort and paginate bugs. `total` counts every matching row."""
    conditions = _filters(query)
    total = session.execute(
        select(func.count())
        .select_from(Bug)
        .outerjoin(ComponentClassification, ComponentClassification.bug_id == Bug.id)
        .outerjoin(SeverityClassification, SeverityClassification.bug_id == Bug.id)
        .where(*conditions)
    ).scalar_one()
    rows = (
        session.execute(
            _read_query()
            .where(*conditions)
            .order_by(*_ordering(query))
            .limit(query.page_size)
            .offset((query.page - 1) * query.page_size)
        )
        .mappings()
        .all()
    )
    return BugPage(
        items=[BugRead.model_validate(dict(row)) for row in rows],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )
