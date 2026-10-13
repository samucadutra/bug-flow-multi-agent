"""Triage runs and run progress (polling and Server-Sent Events)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bugflow.api.deps import get_engine, get_runner, get_session
from bugflow.api.schemas import RunIdsResponse, RunListResponse, TriageRunBody
from bugflow.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, frames, resolve_cursor
from bugflow.enums import RunStatus, RunType
from bugflow.services.background import BackgroundRunner
from bugflow.services.run_events import iter_run_events
from bugflow.services.run_queries import (
    DEFAULT_RUN_LIMIT,
    MAX_RUN_LIMIT,
    MIN_RUN_LIMIT,
    RunDetail,
    get_run_detail,
    list_runs,
)

router = APIRouter(tags=["runs"])


@router.post("/triage-runs", status_code=202, summary="Start triage of one bug or all open bugs")
def start_triage(
    body: Annotated[TriageRunBody, Body()],
    runner: Annotated[BackgroundRunner, Depends(get_runner)],
) -> RunIdsResponse:
    return RunIdsResponse(run_ids=runner.start_run("triage", body.params()).run_ids)


@router.get("/runs", summary="List recent runs, newest first")
def recent_runs(
    session: Annotated[Session, Depends(get_session)],
    type: Annotated[RunType | None, Query()] = None,
    status: Annotated[RunStatus | None, Query()] = None,
    limit: Annotated[int, Query(ge=MIN_RUN_LIMIT, le=MAX_RUN_LIMIT)] = DEFAULT_RUN_LIMIT,
) -> RunListResponse:
    return RunListResponse(items=list_runs(session, type, status, limit))


@router.get("/runs/{id}", summary="Get a run with its steps and logs")
def run_detail(id: int, session: Annotated[Session, Depends(get_session)]) -> RunDetail:
    return get_run_detail(session, id)


@router.get(
    "/runs/{id}/events",
    summary="Stream the progress events of a run",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
def run_events(
    id: int,
    engine: Annotated[Engine, Depends(get_engine)],
    after: Annotated[str | None, Query(description="Cursor of the last event received.")] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    # The run and the cursor are validated here, before the first byte is streamed.
    events = iter_run_events(engine, id, resolve_cursor(after, last_event_id))
    return StreamingResponse(frames(events), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)
