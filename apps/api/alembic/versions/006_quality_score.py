"""judge verdict on run traces

Revision ID: 006
Revises: 005
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable and without a server default, unlike 005: an unjudged turn has
    # no verdict, and backfilling 0.0 would tell the ranking that every answer
    # ever written was judged and found worthless.
    op.add_column("run_traces", sa.Column("quality_score", sa.Float(), nullable=True))
    op.add_column("run_traces", sa.Column("quality_model_id", sa.String(length=128), nullable=True))
    # Индекса нет намеренно: оценки читаются только внутри окна агрегата,
    # которое и так идёт по ix_run_traces_created_at.


def downgrade() -> None:
    op.drop_column("run_traces", "quality_model_id")
    op.drop_column("run_traces", "quality_score")
