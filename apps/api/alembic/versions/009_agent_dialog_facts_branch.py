"""agent dialog facts + branch lineage

Revision ID: 009
Revises: 008
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_dialogs",
        sa.Column(
            "facts",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "agent_dialogs",
        sa.Column("parent_dialog_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "agent_dialogs",
        sa.Column("branch_label", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "agent_dialogs",
        sa.Column("forked_from_message_id", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_agent_dialogs_parent",
        "agent_dialogs",
        "agent_dialogs",
        ["parent_dialog_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_agent_dialogs_parent",
        "agent_dialogs",
        ["parent_dialog_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_dialogs_parent", table_name="agent_dialogs")
    op.drop_constraint("fk_agent_dialogs_parent", "agent_dialogs", type_="foreignkey")
    op.drop_column("agent_dialogs", "forked_from_message_id")
    op.drop_column("agent_dialogs", "branch_label")
    op.drop_column("agent_dialogs", "parent_dialog_id")
    op.drop_column("agent_dialogs", "facts")
