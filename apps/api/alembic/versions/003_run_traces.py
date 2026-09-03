"""run traces for the model pareto lab

Revision ID: 003
Revises: 002
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_traces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("visitor_hash", sa.String(length=64), nullable=True),
        sa.Column("preferred_model", sa.String(length=128), nullable=False),
        sa.Column("resolved_model_id", sa.String(length=128), nullable=True),
        sa.Column(
            "attempts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=True),
        sa.Column("token_count_est", sa.Integer(), nullable=True),
        sa.Column("cost_proxy", sa.Float(), nullable=True),
        sa.Column("tool_rounds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_ok", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_run_traces_created_at", "run_traces", ["created_at"])
    op.create_index(
        "ix_run_traces_session_id_created_at", "run_traces", ["session_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_run_traces_session_id_created_at", table_name="run_traces")
    op.drop_index("ix_run_traces_created_at", table_name="run_traces")
    op.drop_table("run_traces")
