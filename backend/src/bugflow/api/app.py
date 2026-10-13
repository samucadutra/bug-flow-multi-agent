"""Application factory: routers under `/api/v1`, CORS, error handling and the lifespan."""

from __future__ import annotations

import logging
import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from bugflow import __version__
from bugflow.api.errors import UnexpectedErrorMiddleware, install_error_handlers
from bugflow.api.routers import admin, bugs, runs, search, system
from bugflow.config import Settings
from bugflow.db.engine import create_db_engine
from bugflow.logging_config import Redactor
from bugflow.services.background import BackgroundRunner
from bugflow.services.health import LlmProbe
from bugflow.services.llm_client import OpenAILlmClient
from bugflow.services.recovery import recover_interrupted_runs
from bugflow.services.reports import install_report_hook

logger = logging.getLogger("bugflow.api")

API_PREFIX = "/api/v1"
SHUTDOWN_TIMEOUT_SECONDS = 5.0
ALLOWED_METHODS = ["GET", "POST", "PATCH", "OPTIONS"]
ALLOWED_HEADERS = ["Content-Type", "Last-Event-ID"]


def _lazy_client_getter(settings: Settings) -> Callable[[], Any]:
    """Build the LLM client on first use; a missing key raises `ConfigError` at that moment."""
    lock = threading.Lock()
    cache: list[OpenAILlmClient] = []

    def get_client() -> OpenAILlmClient:
        with lock:
            if not cache:
                cache.append(OpenAILlmClient.from_settings(settings))
            return cache[0]

    return get_client


def create_app(
    settings: Settings,
    engine: Engine | None = None,
    *,
    runner: BackgroundRunner | None = None,
    llm_probe: LlmProbe | None = None,
    get_client: Callable[[], Any] | None = None,
    fault: Callable[[], None] | None = None,
) -> FastAPI:
    """Build the API. `runner`, `llm_probe`, `get_client` and `fault` are test injection points."""
    redactor = Redactor(settings.secret_values())
    owns_engine = engine is None
    engine = engine if engine is not None else create_db_engine(settings.database_url)
    client_getter = get_client or _lazy_client_getter(settings)
    owns_runner = runner is None
    if runner is None:
        runner = BackgroundRunner(
            engine, client_getter, redactor, similar_k=settings.similar_bugs_k
        )
    install_report_hook()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        install_report_hook()
        try:
            await run_in_threadpool(recover_interrupted_runs, engine, redactor)
        except Exception as exc:
            text = redactor.redact(str(exc) or type(exc).__name__)
            logger.warning("Startup recovery skipped: %s", text)
        try:
            yield
        finally:
            if owns_runner:
                await run_in_threadpool(runner.shutdown, SHUTDOWN_TIMEOUT_SECONDS)
            if owns_engine:
                engine.dispose()

    app = FastAPI(
        title="BugFlow API",
        version=__version__,
        description="HTTP API of BugFlow: bug management, triage runs, search and operations.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.runner = runner
    app.state.redactor = redactor
    app.state.get_client = client_getter
    app.state.llm_probe = llm_probe
    app.state.fault = fault

    api = APIRouter(prefix=API_PREFIX)
    for module in (system, admin, bugs, search, runs):
        api.include_router(module.router)
    app.include_router(api)

    install_error_handlers(app, redactor)
    # Added first, so it sits inside CORS and its 500 answers still carry the CORS headers.
    app.add_middleware(UnexpectedErrorMiddleware, redactor=redactor)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        allow_credentials=False,
    )
    return app
