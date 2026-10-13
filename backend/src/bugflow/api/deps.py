"""Request dependencies: settings, engine, a session per request, runner and LLM access."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from bugflow.config import Settings
from bugflow.db.engine import session_factory
from bugflow.logging_config import Redactor
from bugflow.services.background import BackgroundRunner
from bugflow.services.health import LlmProbe


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_session(request: Request) -> Iterator[Session]:
    with session_factory(request.app.state.engine)() as session:
        yield session


def get_runner(request: Request) -> BackgroundRunner:
    return request.app.state.runner


def get_redactor(request: Request) -> Redactor:
    return request.app.state.redactor


def get_client_getter(request: Request) -> Callable[[], Any]:
    return request.app.state.get_client


def get_probe(request: Request) -> LlmProbe | None:
    return request.app.state.llm_probe
