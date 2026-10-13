"""Semantic search."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from bugflow.api.deps import get_client_getter, get_session
from bugflow.services.errors import FieldError, ValidationFailedError
from bugflow.services.similarity import (
    DEFAULT_SEARCH_LIMIT,
    MAX_LIMIT,
    MIN_LIMIT,
    SearchResult,
    search_similar,
)

router = APIRouter(tags=["search"])


@router.get("/search", summary="Find the bugs most similar to a text")
def search(
    session: Annotated[Session, Depends(get_session)],
    get_client: Annotated[Callable[[], Any], Depends(get_client_getter)],
    q: Annotated[str, Query(description="Text to search for.")],
    limit: Annotated[int, Query(ge=MIN_LIMIT, le=MAX_LIMIT)] = DEFAULT_SEARCH_LIMIT,
) -> SearchResult:
    try:
        return search_similar(session, get_client, q, limit)
    except ValidationFailedError as exc:
        renamed = [
            FieldError(field="q" if item.field == "text" else item.field, message=item.message)
            for item in exc.field_errors
        ]
        raise ValidationFailedError(renamed) from None
