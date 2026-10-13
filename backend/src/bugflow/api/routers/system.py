"""Health, canonical enums and dashboard stats."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bugflow.api.deps import get_engine, get_probe, get_session, get_settings
from bugflow.api.schemas import (
    EnumEntry,
    EnumsResponse,
    EnumValueOut,
    HealthResponse,
    StatsResponse,
)
from bugflow.config import Settings
from bugflow.enums import all_enums
from bugflow.services.health import LlmProbe, check_health
from bugflow.services.stats import dashboard_stats

router = APIRouter(tags=["system"])


@router.get("/health", summary="Check the database, vector search and LLM connection")
def health(
    settings: Annotated[Settings, Depends(get_settings)],
    engine: Annotated[Engine, Depends(get_engine)],
    probe: Annotated[LlmProbe | None, Depends(get_probe)],
) -> HealthResponse:
    """Always answers 200; a failed check is reported in its own field."""
    report = check_health(settings, engine, probe)
    return HealthResponse(
        ok=report.all_ok,
        database=report.database,
        vector_search=report.vector_search,
        llm=report.llm,
    )


@router.get("/meta/enums", summary="List the canonical enums")
def enums() -> EnumsResponse:
    return EnumsResponse(
        enums=[
            EnumEntry(
                name=descriptor.name,
                values=[
                    EnumValueOut(code=value.code, label=value.label, definition=value.definition)
                    for value in descriptor.values
                ],
            )
            for descriptor in all_enums()
        ]
    )


@router.get("/stats", summary="Count bugs by status, component and severity")
def stats(session: Annotated[Session, Depends(get_session)]) -> StatsResponse:
    return dashboard_stats(session)
