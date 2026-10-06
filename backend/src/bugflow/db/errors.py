"""Database errors. Messages never contain the connection URL, host or credentials."""

from __future__ import annotations


class BugflowDatabaseError(Exception):
    """Base class for database errors raised by the admin services."""


class DatabaseUnavailableError(BugflowDatabaseError):
    def __init__(self) -> None:
        super().__init__("Cannot connect to the database")


class PgvectorUnavailableError(BugflowDatabaseError):
    def __init__(self) -> None:
        super().__init__("pgvector extension is not available; use the pgvector/pgvector image")
