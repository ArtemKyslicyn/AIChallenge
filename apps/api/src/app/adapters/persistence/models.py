"""SQLAlchemy tables. Named ``*Row`` so they never shadow domain entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.cascade import CASCADE_OFF


class Base(DeclarativeBase):
    pass


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    access_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    scenario_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    visitor_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    #: Which model produced this answer. Always set for persisted assistant rows.
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_messages_session_id_created_at", "session_id", "created_at"),)


class RunTraceRow(Base):
    """One measured assistant turn. Deliberately holds no prompt text.

    Both foreign keys cascade: a trace is a measurement *of* a message, and
    keeping it after the message is gone would leave an unjoinable row behind.
    """

    __tablename__ = "run_traces"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    message_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    visitor_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_model: Mapped[str] = mapped_column(String(128), nullable=False)
    #: Null when the whole chain was exhausted and nothing answered.
    resolved_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    #: The router's per-request journal, as written: ``[{model_id, ok, …}]``.
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    ttft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_count_est: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_proxy: Mapped[float | None] = mapped_column(Float, nullable=True)
    tool_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: off | cheap | escalated. The server default matters: rows written before
    #: the cascade existed must read back as "it did not run", not as null.
    cascade_stage: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CASCADE_OFF, server_default=CASCADE_OFF
    )
    cheap_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cheap_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        # The Lab reads a time window across all sessions; the debug view reads
        # one session newest-first. One index each.
        Index("ix_run_traces_created_at", "created_at"),
        Index("ix_run_traces_session_id_created_at", "session_id", "created_at"),
        # The escalation summary filters by stage inside a time window.
        Index("ix_run_traces_cascade_stage", "cascade_stage", "created_at"),
    )


class MessageFeedbackRow(Base):
    """One vote on one assistant message — at most one row per message.

    The uniqueness is the product decision made physical: v1 collects a single
    verdict per answer (last write wins) rather than a vote count, so a reader
    changing their mind updates this row instead of adding a second opinion.
    """

    __tablename__ = "message_feedback"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True)
    message_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    visitor_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    value: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", name="uq_message_feedback_message_id"),
        # The domain only knows two values; the database should refuse a third
        # rather than let a typo become a row nobody can aggregate.
        CheckConstraint("value IN ('up', 'down')", name="ck_message_feedback_value"),
        # Both read paths — the router's window and the export — scan by time.
        Index("ix_message_feedback_created_at", "created_at"),
    )
