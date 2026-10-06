import re

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    PrimaryKeyConstraint,
    UniqueConstraint,
)

from bugflow import enums
from bugflow.db import models  # noqa: F401
from bugflow.db.base import Base

TABLES = {
    "bugs",
    "bug_embeddings",
    "component_classifications",
    "severity_classifications",
    "technical_analyses",
    "resolution_plans",
    "bug_reports",
    "runs",
    "run_steps",
    "run_logs",
}

ENUM_COLUMNS = [
    ("bugs", "environment", enums.Environment),
    ("bugs", "reporting_team", enums.Team),
    ("bugs", "status", enums.BugStatus),
    ("runs", "type", enums.RunType),
    ("runs", "status", enums.RunStatus),
    ("run_steps", "status", enums.StepStatus),
    ("component_classifications", "component", enums.Component),
    ("severity_classifications", "severity", enums.Severity),
    ("resolution_plans", "resolution_status", enums.ResolutionStatus),
    ("resolution_plans", "assigned_team", enums.Team),
    ("resolution_plans", "priority", enums.Priority),
]


def _check(table: str, name: str) -> CheckConstraint:
    found = [
        c
        for c in Base.metadata.tables[table].constraints
        if isinstance(c, CheckConstraint) and c.name == name
    ]
    assert len(found) == 1, f"missing {name}"
    return found[0]


def _literals(constraint: CheckConstraint) -> list[str]:
    return re.findall(r"'([^']*)'", str(constraint.sqltext))


def test_table_set():
    assert set(Base.metadata.tables) == TABLES


def test_every_enum_column_has_check():
    for table, column, enum_cls in ENUM_COLUMNS:
        assert _literals(_check(table, f"ck_{table}_{column}")) == enums.codes(enum_cls)


def test_seniority_check_covers_assignee_profile():
    check = _check("resolution_plans", "ck_resolution_plans_assignee_seniority")
    assert "seniority" in str(check.sqltext)
    assert _literals(check)[1:] == enums.codes(enums.Seniority)


def test_constraint_names_follow_convention():
    patterns = {
        "pk": r"pk_{t}",
        "fk": r"fk_{t}_\w+",
        "ck": r"ck_{t}_\w+",
        "uq": r"uq_{t}_\w+",
    }
    for table in Base.metadata.sorted_tables:
        for constraint in table.constraints:
            kind = {
                PrimaryKeyConstraint: "pk",
                ForeignKeyConstraint: "fk",
                CheckConstraint: "ck",
                UniqueConstraint: "uq",
            }[type(constraint)]
            assert constraint.name, f"unnamed constraint on {table.name}"
            assert re.fullmatch(patterns[kind].format(t=table.name), constraint.name)
        for index in table.indexes:
            assert index.name and re.fullmatch(rf"ix_{table.name}_\w+", index.name)


def test_embedding_dimension():
    column = Base.metadata.tables["bug_embeddings"].c.embedding
    assert isinstance(column.type, Vector)
    assert column.type.dim == 1536


def test_bug_column_limits():
    columns = Base.metadata.tables["bugs"].c
    assert columns.title.type.length == 120
    assert columns.description.type.length == 5000
    assert columns.reproduction_steps.type.length == 5000
    assert columns.system_version.type.length == 50
