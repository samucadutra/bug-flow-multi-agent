"""ORM models for the ten application tables. The single schema definition for the application."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from bugflow.db.base import Base, enum_check, quote_literals
from bugflow.enums import (
    BugStatus,
    Component,
    Environment,
    Priority,
    ResolutionStatus,
    RunStatus,
    RunType,
    Seniority,
    Severity,
    StepStatus,
    Team,
)

EMBEDDING_DIMENSIONS = 1536


def _now_column() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def _array_check(column: str) -> CheckConstraint:
    return CheckConstraint(f"jsonb_typeof({column}) = 'array'", name=column)


class Bug(Base):
    __tablename__ = "bugs"
    __table_args__ = (
        enum_check("environment", Environment),
        enum_check("reporting_team", Team),
        enum_check("status", BugStatus),
        Index("ix_bugs_status", "status"),
        Index("ix_bugs_opened_at", "opened_at"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(5000), nullable=False)
    reproduction_steps: Mapped[str] = mapped_column(String(5000), nullable=False)
    system_version: Mapped[str] = mapped_column(String(50), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    reporting_team: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{BugStatus.OPEN.value}'")
    )
    opened_at: Mapped[datetime] = _now_column()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        enum_check("type", RunType),
        enum_check("status", RunStatus),
        CheckConstraint("progress_done >= 0", name="progress_done"),
        CheckConstraint("progress_total >= 0", name="progress_total"),
        Index("ix_runs_bug_id", "bug_id"),
        Index("ix_runs_started_at", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    bug_id: Mapped[int | None] = mapped_column(ForeignKey("bugs.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{RunStatus.QUEUED.value}'")
    )
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = _now_column()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BugEmbedding(Base):
    __tablename__ = "bug_embeddings"

    bug_id: Mapped[int] = mapped_column(ForeignKey("bugs.id", ondelete="CASCADE"), primary_key=True)
    embedding: Mapped[Any] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedded_at: Mapped[datetime] = _now_column()


class ComponentClassification(Base):
    __tablename__ = "component_classifications"
    __table_args__ = (enum_check("component", Component),)

    bug_id: Mapped[int] = mapped_column(ForeignKey("bugs.id", ondelete="CASCADE"), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    component: Mapped[str] = mapped_column(String(20), nullable=False)
    justification: Mapped[str] = mapped_column(String(600), nullable=False)
    created_at: Mapped[datetime] = _now_column()


class SeverityClassification(Base):
    __tablename__ = "severity_classifications"
    __table_args__ = (enum_check("severity", Severity),)

    bug_id: Mapped[int] = mapped_column(ForeignKey("bugs.id", ondelete="CASCADE"), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    justification: Mapped[str] = mapped_column(String(600), nullable=False)
    user_impact: Mapped[str] = mapped_column(String(400), nullable=False)
    created_at: Mapped[datetime] = _now_column()


class TechnicalAnalysis(Base):
    __tablename__ = "technical_analyses"
    __table_args__ = (
        _array_check("debugging_approach"),
        _array_check("side_effects"),
        _array_check("referenced_similar_bug_ids"),
    )

    bug_id: Mapped[int] = mapped_column(ForeignKey("bugs.id", ondelete="CASCADE"), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    root_cause: Mapped[str] = mapped_column(String(800), nullable=False)
    technical_impact: Mapped[str] = mapped_column(String(600), nullable=False)
    debugging_approach: Mapped[Any] = mapped_column(JSONB, nullable=False)
    proposed_solution: Mapped[str] = mapped_column(String(800), nullable=False)
    side_effects: Mapped[Any] = mapped_column(JSONB, nullable=False)
    referenced_similar_bug_ids: Mapped[Any] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _now_column()


class ResolutionPlan(Base):
    __tablename__ = "resolution_plans"
    __table_args__ = (
        enum_check("resolution_status", ResolutionStatus),
        enum_check("assigned_team", Team),
        enum_check("priority", Priority),
        CheckConstraint("target_days BETWEEN 1 AND 90", name="target_days"),
        CheckConstraint("jsonb_typeof(assignee_profile) = 'object'", name="assignee_profile"),
        CheckConstraint(
            f"assignee_profile->>'seniority' IN "
            f"({quote_literals([member.value for member in Seniority])})",
            name="assignee_seniority",
        ),
    )

    bug_id: Mapped[int] = mapped_column(ForeignKey("bugs.id", ondelete="CASCADE"), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    resolution_status: Mapped[str] = mapped_column(String(20), nullable=False)
    assigned_team: Mapped[str] = mapped_column(String(20), nullable=False)
    assignee_profile: Mapped[Any] = mapped_column(JSONB, nullable=False)
    target_days: Mapped[int] = mapped_column(Integer, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[str] = mapped_column(String(600), nullable=False, server_default=text("''"))
    created_at: Mapped[datetime] = _now_column()


class BugReport(Base):
    __tablename__ = "bug_reports"
    __table_args__ = (_array_check("key_takeaways"), _array_check("next_steps"))

    bug_id: Mapped[int] = mapped_column(ForeignKey("bugs.id", ondelete="CASCADE"), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), nullable=False)
    executive_summary: Mapped[str] = mapped_column(String(600), nullable=False)
    key_takeaways: Mapped[Any] = mapped_column(JSONB, nullable=False)
    next_steps: Mapped[Any] = mapped_column(JSONB, nullable=False)
    markdown: Mapped[str | None] = mapped_column(Text)
    html: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_column()


class RunStep(Base):
    __tablename__ = "run_steps"
    __table_args__ = (
        enum_check("status", StepStatus),
        CheckConstraint("position >= 1", name="position"),
        CheckConstraint("duration_ms >= 0", name="duration_ms"),
        UniqueConstraint("run_id", "position"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(always=False), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text(f"'{StepStatus.PENDING.value}'")
    )
    input: Mapped[Any | None] = mapped_column(JSONB)
    output: Mapped[Any | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)


class RunLog(Base):
    __tablename__ = "run_logs"
    __table_args__ = (Index("ix_run_logs_run_id_id", "run_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
