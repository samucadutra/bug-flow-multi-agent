"""Bug endpoints: create, list, detail, edit, similar, runs, reopen and report."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Query, Request, Response
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bugflow.api.deps import get_client_getter, get_engine, get_session, get_settings
from bugflow.api.schemas import (
    ConfirmBody,
    ReportFormatQuery,
    ReportJson,
    RunListResponse,
    SimilarResponse,
)
from bugflow.config import Settings
from bugflow.services.bug_detail import BugDetail, get_bug_detail
from bugflow.services.bugs import create_bug, list_bugs, update_bug
from bugflow.services.reopen import reopen_bug
from bugflow.services.reports import ReportFormat, get_report
from bugflow.services.run_queries import list_bug_runs
from bugflow.services.schemas import (
    BugCreate,
    BugListQuery,
    BugPage,
    BugRead,
    BugUpdate,
    validate_payload,
)
from bugflow.services.similarity import MAX_LIMIT, MIN_LIMIT, similar_to_bug

router = APIRouter(tags=["bugs"])


def _create_body() -> Any:
    return Body(json_schema_extra=BugCreate.model_json_schema())


def _update_body() -> Any:
    return Body(json_schema_extra=BugUpdate.model_json_schema())


@router.get("/bugs", summary="List bugs with filters, search, sorting and paging")
def bugs(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    status: Annotated[str | None, Query()] = None,
    component: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
    environment: Annotated[str | None, Query()] = None,
    reporting_team: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    sort_by: Annotated[str | None, Query()] = None,
    sort_dir: Annotated[str | None, Query()] = None,
    page: Annotated[str | None, Query()] = None,
    page_size: Annotated[str | None, Query()] = None,
) -> BugPage:
    fault = request.app.state.fault
    if fault is not None:
        fault()
    values = {
        "status": status,
        "component": component,
        "severity": severity,
        "environment": environment,
        "reporting_team": reporting_team,
        "search": search,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "page": page,
        "page_size": page_size,
    }
    query = validate_payload(BugListQuery, {k: v for k, v in values.items() if v is not None})
    return list_bugs(session, query)


@router.post("/bugs", status_code=201, summary="Create a bug")
def create(
    payload: Annotated[dict[str, Any], _create_body()],
    session: Annotated[Session, Depends(get_session)],
) -> BugRead:
    data = validate_payload(BugCreate, payload)
    bug = create_bug(session, data)
    session.commit()
    return bug


@router.get("/bugs/{id}", summary="Get a bug with its stored results")
def detail(id: int, session: Annotated[Session, Depends(get_session)]) -> BugDetail:
    return get_bug_detail(session, id)


@router.patch("/bugs/{id}", summary="Edit an open bug")
def edit(
    id: int,
    payload: Annotated[dict[str, Any], _update_body()],
    session: Annotated[Session, Depends(get_session)],
) -> BugRead:
    data = validate_payload(BugUpdate, payload)
    bug = update_bug(session, id, data)
    session.commit()
    return bug


@router.get("/bugs/{id}/similar", summary="Find bugs similar to a bug")
def similar(
    id: int,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    get_client: Annotated[Callable[[], Any], Depends(get_client_getter)],
    limit: Annotated[int | None, Query(ge=MIN_LIMIT, le=MAX_LIMIT)] = None,
) -> SimilarResponse:
    k = limit if limit is not None else settings.similar_bugs_k
    items = similar_to_bug(session, get_client, id, k)
    session.commit()
    return SimilarResponse(items=items)


@router.get("/bugs/{id}/runs", summary="List the runs of a bug, newest first")
def bug_runs(id: int, session: Annotated[Session, Depends(get_session)]) -> RunListResponse:
    return RunListResponse(items=list_bug_runs(session, id))


@router.post("/bugs/{id}/reopen", summary="Reopen a processed or failed bug")
def reopen(
    id: int,
    body: Annotated[ConfirmBody, Body()],
    engine: Annotated[Engine, Depends(get_engine)],
) -> BugRead:
    return reopen_bug(engine, id)


@router.get(
    "/bugs/{id}/report",
    summary="Get the report of a processed bug",
    response_model=ReportJson,
    responses={200: {"content": {"text/markdown": {}, "text/html": {}}}},
)
def report(
    id: int,
    session: Annotated[Session, Depends(get_session)],
    format: Annotated[ReportFormatQuery, Query()] = ReportFormatQuery.JSON,
) -> Response | ReportJson:
    if format is ReportFormatQuery.JSON:
        markdown = get_report(session, id, ReportFormat.MD)
        html = get_report(session, id, ReportFormat.HTML)
        if markdown.rendered or html.rendered:
            session.commit()
        return ReportJson(bug_id=id, markdown=markdown.content, html=html.content)
    wanted = ReportFormat.MD if format is ReportFormatQuery.MD else ReportFormat.HTML
    result = get_report(session, id, wanted)
    if result.rendered:
        session.commit()
    media_type = "text/markdown" if wanted is ReportFormat.MD else "text/html"
    return Response(content=result.content.encode("utf-8"), media_type=media_type)
