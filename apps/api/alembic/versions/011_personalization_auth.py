"""Day 12 — users, auth tokens, preference profiles, owner key widen.

Revision ID: 011
Revises: 010
Create Date: 2026-09-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "agent_dialogs",
        "client_visitor_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=64),
        existing_nullable=False,
    )
    op.add_column(
        "agent_dialogs",
        sa.Column("active_lens_id", sa.String(length=32), nullable=True),
    )
    op.alter_column(
        "agent_long_term_memory",
        "client_visitor_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=64),
        existing_nullable=False,
    )

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])

    op.create_table(
        "agent_preference_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("style", sa.Text(), nullable=False, server_default=""),
        sa.Column("format", sa.Text(), nullable=False, server_default=""),
        sa.Column("constraints", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_key", "name", name="uq_agent_preference_owner_name"),
    )
    op.create_index(
        "ix_agent_preference_profiles_owner",
        "agent_preference_profiles",
        ["owner_key", "is_active"],
    )

    op.create_foreign_key(
        "fk_sessions_user_id_users",
        "sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_sessions_user_id_users", "sessions", type_="foreignkey")
    op.drop_index("ix_agent_preference_profiles_owner", table_name="agent_preference_profiles")
    op.drop_table("agent_preference_profiles")
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_table("users")
    op.drop_column("agent_dialogs", "active_lens_id")
    op.alter_column(
        "agent_long_term_memory",
        "client_visitor_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.alter_column(
        "agent_dialogs",
        "client_visitor_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
