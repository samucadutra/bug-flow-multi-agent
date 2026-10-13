"""Administrative operations: init, seed, reset and index."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends
from sqlalchemy import Engine

from bugflow.api.deps import get_engine, get_redactor, get_runner
from bugflow.api.schemas import ConfirmBody, InitResponse, RunIdsResponse
from bugflow.logging_config import Redactor
from bugflow.services.background import BackgroundRunner
from bugflow.services.operations import init_messages, run_init, run_reset

router = APIRouter(prefix="/admin", tags=["admin"])


def _release_connections(engine: Engine) -> None:
    """Schema changes invalidate cached type ids of pooled connections; start fresh."""
    engine.dispose()


@router.post("/db/init", summary="Apply database migrations")
def init_database(
    engine: Annotated[Engine, Depends(get_engine)],
    redactor: Annotated[Redactor, Depends(get_redactor)],
) -> InitResponse:
    result = run_init(engine, redactor)
    _release_connections(engine)
    return InitResponse(applied_revisions=result.applied_revisions, messages=init_messages(result))


@router.post("/db/seed", status_code=202, summary="Load the sample bugs in the background")
def seed_database(runner: Annotated[BackgroundRunner, Depends(get_runner)]) -> RunIdsResponse:
    return RunIdsResponse(run_ids=runner.start_run("seed").run_ids)


@router.post("/db/reset", summary="Delete all data and recreate an empty schema")
def reset_database(
    body: Annotated[ConfirmBody, Body()],
    engine: Annotated[Engine, Depends(get_engine)],
    redactor: Annotated[Redactor, Depends(get_redactor)],
) -> InitResponse:
    result = run_reset(engine, redactor)
    _release_connections(engine)
    return InitResponse(applied_revisions=result.applied_revisions, messages=init_messages(result))


@router.post("/index", status_code=202, summary="Rebuild the embedding index in the background")
def index_bugs(runner: Annotated[BackgroundRunner, Depends(get_runner)]) -> RunIdsResponse:
    return RunIdsResponse(run_ids=runner.start_run("index").run_ids)
