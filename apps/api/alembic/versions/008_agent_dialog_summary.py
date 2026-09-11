"""agent dialog rolling summary columns

Revision ID: 008
Revises: 007
Create Date: 2026-09-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_dialogs",
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_dialogs",
        sa.Column(
            "summary_until_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_dialogs", "summary_until_count")
    op.drop_column("agent_dialogs", "summary_text")
