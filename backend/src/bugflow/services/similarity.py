"""Similarity search over stored embeddings: `search_similar` and `similar_to_bug`."""

from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bugflow.db.models import Bug, BugEmbedding
from bugflow.services.embeddings import (
    EmbeddingClient,
    ensure_embedding,
    query_text,
)
from bugflow.services.errors import EmptySearchTextError, FieldError, ValidationFailedError

DEFAULT_SEARCH_LIMIT = 5
MIN_LIMIT = 1
MAX_LIMIT = 20
MAX_TEXT_LENGTH = 500
NOT_INDEXED_HINT = "No bugs are indexed; run index"


class SimilarBug(BaseModel):
    model_config = ConfigDict(frozen=True)

    bug_id: int
    title: str
    status: str
    score: float


class SearchResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[SimilarBug]
    hint: str = ""


def _limit_error(limit: int) -> FieldError | None:
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        return FieldError(field="limit", message=f"must be between {MIN_LIMIT} and {MAX_LIMIT}")
    return None


def validate_search(text: str, limit: int) -> str:
    """Return the trimmed query text, or raise before any index check or API call."""
    query = query_text(text)
    if not query:
        raise EmptySearchTextError()
    errors = []
    if len(query) > MAX_TEXT_LENGTH:
        errors.append(
            FieldError(field="text", message=f"must be at most {MAX_TEXT_LENGTH} characters")
        )
    limit_error = _limit_error(limit)
    if limit_error is not None:
        errors.append(limit_error)
    if errors:
        raise ValidationFailedError(errors)
    return query


def _nearest(session: Session, target, limit: int, exclude_bug_id: int | None) -> list[SimilarBug]:
    distance = BugEmbedding.embedding.cosine_distance(target)
    statement = (
        select(Bug.id, Bug.title, Bug.status, (1 - distance).label("score"))
        .join(Bug, Bug.id == BugEmbedding.bug_id)
        .order_by(distance, Bug.id)
        .limit(limit)
    )
    if exclude_bug_id is not None:
        statement = statement.where(BugEmbedding.bug_id != exclude_bug_id)
    return [
        SimilarBug(bug_id=row.id, title=row.title, status=row.status, score=float(row.score))
        for row in session.execute(statement)
    ]


def search_similar(
    session: Session,
    get_client: Callable[[], EmbeddingClient],
    text: str,
    k: int = DEFAULT_SEARCH_LIMIT,
) -> SearchResult:
    """Top `k` indexed bugs by cosine similarity to the text."""
    query = validate_search(text, k)
    if session.scalar(select(func.count()).select_from(BugEmbedding)) == 0:
        return SearchResult(items=[], hint=NOT_INDEXED_HINT)
    (vector,) = get_client().embed([query])
    return SearchResult(items=_nearest(session, vector, k, None))


def similar_to_bug(
    session: Session,
    get_client: Callable[[], EmbeddingClient],
    bug_id: int,
    k: int = DEFAULT_SEARCH_LIMIT,
) -> list[SimilarBug]:
    """Top `k` other indexed bugs; the bug's own embedding is refreshed first if stale."""
    limit_error = _limit_error(k)
    if limit_error is not None:
        raise ValidationFailedError([limit_error])
    ensure_embedding(session, get_client(), bug_id)
    own = select(BugEmbedding.embedding).where(BugEmbedding.bug_id == bug_id).scalar_subquery()
    return _nearest(session, own, k, bug_id)
