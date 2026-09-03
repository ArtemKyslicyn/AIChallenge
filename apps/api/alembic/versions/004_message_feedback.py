"""message feedback votes

Revision ID: 004
Revises: 003
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("visitor_hash", sa.String(length=64), nullable=True),
        sa.Column("value", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # One verdict per answer: a reader changing their mind updates the row.
        sa.UniqueConstraint("message_id", name="uq_message_feedback_message_id"),
        sa.CheckConstraint("value IN ('up', 'down')", name="ck_message_feedback_value"),
    )
    op.create_index("ix_message_feedback_created_at", "message_feedback", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_message_feedback_created_at", table_name="message_feedback")
    op.drop_table("message_feedback")
