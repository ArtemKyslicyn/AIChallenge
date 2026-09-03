"""cascade fields on run traces

Revision ID: 005
Revises: 004
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default backfills existing rows: a turn from before the cascade
    # existed is "off", never null.
    op.add_column(
        "run_traces",
        sa.Column("cascade_stage", sa.String(length=16), nullable=False, server_default="off"),
    )
    op.add_column("run_traces", sa.Column("cheap_model_id", sa.String(length=128), nullable=True))
    op.add_column("run_traces", sa.Column("cheap_score", sa.Float(), nullable=True))
    # Сводка эскалаций читает окно по времени и фильтрует по стадии.
    op.create_index("ix_run_traces_cascade_stage", "run_traces", ["cascade_stage", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_run_traces_cascade_stage", table_name="run_traces")
    op.drop_column("run_traces", "cheap_score")
    op.drop_column("run_traces", "cheap_model_id")
    op.drop_column("run_traces", "cascade_stage")
