"""Declarative base, constraint naming convention and CHECK helpers."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import CheckConstraint, Column, MetaData, String, Table
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def quote_literals(values: list[str]) -> str:
    """Render fixed codes (from the canonical enums only) as SQL string literals."""
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def enum_check(column: str, enum_cls: type[StrEnum]) -> CheckConstraint:
    """CHECK constraint limiting `column` to the codes of `enum_cls`.

    The final name is `ck_<table>_<column>` through the naming convention.
    """
    codes = quote_literals([member.value for member in enum_cls])
    return CheckConstraint(f"{column} IN ({codes})", name=column)


VERSION_TABLE_NAME = "alembic_version"


def version_table() -> Table:
    """Handle for Alembic's bookkeeping table (a fixed name, used only to drop it)."""
    return Table(VERSION_TABLE_NAME, MetaData(), Column("version_num", String(32)))
