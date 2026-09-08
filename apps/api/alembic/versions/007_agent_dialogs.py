"""agent dialogs with JSONB message history

Revision ID: 007
Revises: 006
Create Date: 2026-09-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_dialogs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        # Browser client id from X-Visitor-Id — primary owner (stable across IP).
        sa.Column("client_visitor_id", sa.String(length=36), nullable=False),
        # Same HMAC as chat sessions (client id + hashed IP) — correlation / analytics.
        sa.Column("visitor_hash", sa.String(length=64), nullable=True),
        sa.Column("client_draft_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("preferred_model", sa.String(length=128), nullable=False, server_default="auto"),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        # [{id, role, content, model_id?, created_at}]
        sa.Column(
            "messages",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "client_visitor_id",
            "client_draft_id",
            name="uq_agent_dialogs_visitor_draft",
        ),
    )
    op.create_index(
        "ix_agent_dialogs_client_updated",
        "agent_dialogs",
        ["client_visitor_id", "updated_at"],
    )
    op.create_index(
        "ix_agent_dialogs_visitor_hash",
        "agent_dialogs",
        ["visitor_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_dialogs_visitor_hash", table_name="agent_dialogs")
    op.drop_index("ix_agent_dialogs_client_updated", table_name="agent_dialogs")
    op.drop_table("agent_dialogs")
