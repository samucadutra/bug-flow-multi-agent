"""Initial schema: vector extension and the ten application tables.

Revision ID: 0001
Revises:
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NOW = sa.text("now()")


def _ts(name: str, *, nullable: bool = False, default: bool = True) -> sa.Column:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=NOW if default else None,
    )


def _bug_pk() -> sa.Column:
    return sa.Column("bug_id", sa.Integer(), nullable=False)


def _bug_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["bug_id"], ["bugs.id"], name=op.f(f"fk_{table}_bug_id"), ondelete="CASCADE"
    )


def _run_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(["run_id"], ["runs.id"], name=op.f(f"fk_{table}_run_id"))


def _ck(table: str, name: str, expression: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(expression, name=op.f(f"ck_{table}_{name}"))


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "bugs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(5000), nullable=False),
        sa.Column("reproduction_steps", sa.String(5000), nullable=False),
        sa.Column("system_version", sa.String(50), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("reporting_team", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'open'")),
        _ts("opened_at"),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bugs")),
        _ck(
            "bugs",
            "environment",
            "environment IN ('production', 'staging', 'development', 'testing')",
        ),
        _ck(
            "bugs",
            "reporting_team",
            "reporting_team IN ('frontend', 'backend', 'data', 'devops', 'security', 'qa', "
            "'support', 'product')",
        ),
        _ck("bugs", "status", "status IN ('open', 'processing', 'processed', 'failed')"),
    )
    op.create_index("ix_bugs_status", "bugs", ["status"])
    op.create_index("ix_bugs_opened_at", "bugs", ["opened_at"])

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("bug_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("progress_done", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sa.Text(), nullable=True),
        _ts("started_at"),
        _ts("finished_at", nullable=True, default=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
        sa.ForeignKeyConstraint(
            ["bug_id"], ["bugs.id"], name=op.f("fk_runs_bug_id"), ondelete="SET NULL"
        ),
        _ck("runs", "type", "type IN ('triage', 'index', 'seed', 'init', 'reset')"),
        _ck("runs", "status", "status IN ('queued', 'running', 'succeeded', 'failed')"),
        _ck("runs", "progress_done", "progress_done >= 0"),
        _ck("runs", "progress_total", "progress_total >= 0"),
    )
    op.create_index("ix_runs_bug_id", "runs", ["bug_id"])
    op.create_index("ix_runs_started_at", "runs", ["started_at"])

    op.create_table(
        "bug_embeddings",
        _bug_pk(),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False),
        _ts("embedded_at"),
        sa.PrimaryKeyConstraint("bug_id", name=op.f("pk_bug_embeddings")),
        _bug_fk("bug_embeddings"),
    )

    op.create_table(
        "component_classifications",
        _bug_pk(),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("component", sa.String(20), nullable=False),
        sa.Column("justification", sa.String(600), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("bug_id", name=op.f("pk_component_classifications")),
        _bug_fk("component_classifications"),
        _run_fk("component_classifications"),
        _ck(
            "component_classifications",
            "component",
            "component IN ('frontend', 'backend', 'database', 'devops', 'security', "
            "'integration', 'ui_ux', 'infrastructure')",
        ),
    )

    op.create_table(
        "severity_classifications",
        _bug_pk(),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("justification", sa.String(600), nullable=False),
        sa.Column("user_impact", sa.String(400), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("bug_id", name=op.f("pk_severity_classifications")),
        _bug_fk("severity_classifications"),
        _run_fk("severity_classifications"),
        _ck(
            "severity_classifications",
            "severity",
            "severity IN ('critical', 'major', 'minor')",
        ),
    )

    op.create_table(
        "technical_analyses",
        _bug_pk(),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("root_cause", sa.String(800), nullable=False),
        sa.Column("technical_impact", sa.String(600), nullable=False),
        sa.Column("debugging_approach", postgresql.JSONB(), nullable=False),
        sa.Column("proposed_solution", sa.String(800), nullable=False),
        sa.Column("side_effects", postgresql.JSONB(), nullable=False),
        sa.Column("referenced_similar_bug_ids", postgresql.JSONB(), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("bug_id", name=op.f("pk_technical_analyses")),
        _bug_fk("technical_analyses"),
        _run_fk("technical_analyses"),
        _ck(
            "technical_analyses",
            "debugging_approach",
            "jsonb_typeof(debugging_approach) = 'array'",
        ),
        _ck("technical_analyses", "side_effects", "jsonb_typeof(side_effects) = 'array'"),
        _ck(
            "technical_analyses",
            "referenced_similar_bug_ids",
            "jsonb_typeof(referenced_similar_bug_ids) = 'array'",
        ),
    )

    op.create_table(
        "resolution_plans",
        _bug_pk(),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("resolution_status", sa.String(20), nullable=False),
        sa.Column("assigned_team", sa.String(20), nullable=False),
        sa.Column("assignee_profile", postgresql.JSONB(), nullable=False),
        sa.Column("target_days", sa.Integer(), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("notes", sa.String(600), nullable=False, server_default=sa.text("''")),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("bug_id", name=op.f("pk_resolution_plans")),
        _bug_fk("resolution_plans"),
        _run_fk("resolution_plans"),
        _ck(
            "resolution_plans",
            "resolution_status",
            "resolution_status IN ('planned', 'needs_info', 'deferred', 'wont_fix')",
        ),
        _ck(
            "resolution_plans",
            "assigned_team",
            "assigned_team IN ('frontend', 'backend', 'data', 'devops', 'security', 'qa', "
            "'support', 'product')",
        ),
        _ck("resolution_plans", "priority", "priority IN ('urgent', 'high', 'medium', 'low')"),
        _ck("resolution_plans", "target_days", "target_days BETWEEN 1 AND 90"),
        _ck(
            "resolution_plans",
            "assignee_profile",
            "jsonb_typeof(assignee_profile) = 'object'",
        ),
        _ck(
            "resolution_plans",
            "assignee_seniority",
            "assignee_profile->>'seniority' IN ('junior', 'mid', 'senior', 'lead')",
        ),
    )

    op.create_table(
        "bug_reports",
        _bug_pk(),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("executive_summary", sa.String(600), nullable=False),
        sa.Column("key_takeaways", postgresql.JSONB(), nullable=False),
        sa.Column("next_steps", postgresql.JSONB(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=True),
        sa.Column("html", sa.Text(), nullable=True),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("bug_id", name=op.f("pk_bug_reports")),
        _bug_fk("bug_reports"),
        _run_fk("bug_reports"),
        _ck("bug_reports", "key_takeaways", "jsonb_typeof(key_takeaways) = 'array'"),
        _ck("bug_reports", "next_steps", "jsonb_typeof(next_steps) = 'array'"),
    )

    op.create_table(
        "run_steps",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("agent_key", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("input", postgresql.JSONB(), nullable=True),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        _ts("started_at", nullable=True, default=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_steps")),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_run_steps_run_id"), ondelete="CASCADE"
        ),
        sa.UniqueConstraint("run_id", "position", name=op.f("uq_run_steps_run_id_position")),
        _ck(
            "run_steps",
            "status",
            "status IN ('pending', 'running', 'succeeded', 'failed', 'skipped')",
        ),
        _ck("run_steps", "position", "position >= 1"),
        _ck("run_steps", "duration_ms", "duration_ms >= 0"),
    )

    op.create_table(
        "run_logs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        _ts("logged_at"),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_logs")),
        sa.ForeignKeyConstraint(
            ["run_id"], ["runs.id"], name=op.f("fk_run_logs_run_id"), ondelete="CASCADE"
        ),
    )
    op.create_index("ix_run_logs_run_id_id", "run_logs", ["run_id", "id"])


def downgrade() -> None:
    for table in (
        "run_logs",
        "run_steps",
        "bug_reports",
        "resolution_plans",
        "technical_analyses",
        "severity_classifications",
        "component_classifications",
        "bug_embeddings",
        "runs",
        "bugs",
    ):
        op.drop_table(table)
