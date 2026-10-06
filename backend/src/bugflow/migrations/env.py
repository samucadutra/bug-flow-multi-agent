"""Alembic environment.

The caller supplies a live connection through `config.attributes["connection"]`. This module
never reads environment variables or builds connection URLs.
"""

from __future__ import annotations

from alembic import context

from bugflow.db import models  # noqa: F401  (registers every table on the metadata)
from bugflow.db.base import Base

target_metadata = Base.metadata


def run_migrations() -> None:
    connection = context.config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("No database connection supplied to the migration environment")
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        transactional_ddl=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations()
