"""session visitor hash and title for chat history

Revision ID: 002
Revises: 001
Create Date: 2026-09-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sessions", sa.Column("visitor_hash", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("ip_hash", sa.String(length=64), nullable=True))
    op.add_column("sessions", sa.Column("title", sa.String(length=120), nullable=True))
    op.create_index(
        "ix_sessions_visitor_hash_created_at",
        "sessions",
        ["visitor_hash", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_visitor_hash_created_at", table_name="sessions")
    op.drop_column("sessions", "title")
    op.drop_column("sessions", "ip_hash")
    op.drop_column("sessions", "visitor_hash")
