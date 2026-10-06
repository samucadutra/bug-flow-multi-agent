"""Reopen service: return a `processed` or `failed` bug to `open` and delete its results.

One transaction: a conditional status update (which also locks the bug row), the deletion of the
five result tables from a hard-coded allowlist, the registered hooks, then the commit. Runs, run
steps, run logs and embeddings are never touched and no run is created. Any failure after the
transaction started rolls everything back.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from sqlalchemy import Engine, delete, select, update
from sqlalchemy import func as sql_func
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.orm import Session

from bugflow.db.engine import session_factory
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.db.models import (
    Bug,
    BugReport,
    ComponentClassification,
    ResolutionPlan,
    SeverityClassification,
    TechnicalAnalysis,
)
from bugflow.enums import BugStatus
from bugflow.services.bugs import ALLOWED_TRANSITIONS, get_bug
from bugflow.services.errors import NotFoundError, ServiceError, StateConflictError
from bugflow.services.schemas import BugRead

logger = logging.getLogger(__name__)

# The only tables reopen deletes from. `BugEmbedding` is deliberately absent.
RESULT_MODELS = (
    ComponentClassification,
    SeverityClassification,
    TechnicalAnalysis,
    ResolutionPlan,
    BugReport,
)
REOPENABLE_STATUSES = tuple(
    sorted(
        status.value for status, targets in ALLOWED_TRANSITIONS.items() if BugStatus.OPEN in targets
    )
)

ReopenHook = Callable[[Session, int], None]
_REOPEN_HOOKS: list[ReopenHook] = []


class ReopenFailedError(ServiceError):
    """The reopen transaction failed and was rolled back."""

    def __init__(self, bug_id: int) -> None:
        super().__init__(reopen_failed_message(bug_id))


def reopen_failed_message(bug_id: int) -> str:
    return f"Reopen of bug {bug_id} failed; nothing was changed"


def processing_message(bug_id: int) -> str:
    return f"Bug {bug_id} is being processed and cannot be reopened"


def already_open_message(bug_id: int) -> str:
    return f"Bug {bug_id} is already open"


def register_reopen_hook(hook: ReopenHook) -> None:
    """Register a hook run inside the reopen transaction, in registration order."""
    _REOPEN_HOOKS.append(hook)


def unregister_reopen_hook(hook: ReopenHook) -> None:
    if hook in _REOPEN_HOOKS:
        _REOPEN_HOOKS.remove(hook)


def clear_reopen_hooks() -> None:
    _REOPEN_HOOKS.clear()


def reopen_bug(engine: Engine, bug_id: int) -> BugRead:
    """Reopen a `processed` or `failed` bug in its own transaction."""
    unreachable = False
    current: str | None = None
    try:
        with session_factory(engine)() as session:
            reopened = session.execute(
                update(Bug)
                .where(Bug.id == bug_id, Bug.status.in_(REOPENABLE_STATUSES))
                .values(status=BugStatus.OPEN.value, updated_at=sql_func.clock_timestamp())
                .returning(Bug.id)
            ).first()
            if reopened is not None:
                try:
                    for model in RESULT_MODELS:
                        session.execute(delete(model).where(model.bug_id == bug_id))
                    for hook in list(_REOPEN_HOOKS):
                        hook(session, bug_id)
                    session.commit()
                except Exception as exc:
                    session.rollback()
                    raise ReopenFailedError(bug_id) from exc
                logger.info("bug %s reopened", bug_id)
                return get_bug(session, bug_id)
            current = session.scalar(select(Bug.status).where(Bug.id == bug_id))
    except (OperationalError, InterfaceError):
        unreachable = True
    if unreachable:
        raise DatabaseUnavailableError()
    if current is None:
        raise NotFoundError(f"Bug {bug_id} not found")
    if current == BugStatus.PROCESSING.value:
        raise StateConflictError(processing_message(bug_id))
    raise StateConflictError(already_open_message(bug_id))
