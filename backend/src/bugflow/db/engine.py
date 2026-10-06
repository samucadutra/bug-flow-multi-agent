"""Engine and session helpers. The URL is passed in; the environment is never read."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

CONNECT_TIMEOUT_SECONDS = 10


def create_db_engine(url: str) -> Engine:
    """Build an engine whose driver gives up connecting after a fixed timeout."""
    return create_engine(
        url, pool_pre_ping=True, connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    )


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
