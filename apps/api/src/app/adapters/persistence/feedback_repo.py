"""Feedback repository: one vote per message, plus the two reads over it.

Like the other repositories here, writes flush but never commit — the caller
owns the transaction.

The two reads pull in opposite directions and are shaped differently on
purpose. ``stats_by_model`` runs on the request path of every chat, so the
counting happens in SQL and only a handful of rows come back. ``export_rows``
is an operator action, so it favours a readable join and a hard row cap over
cleverness.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.adapters.persistence.models import MessageFeedbackRow, MessageRow, RunTraceRow
from app.adapters.persistence.trace_repo import attempt_from_json
from app.domain.entities import MessageRole
from app.domain.feedback import (
    FeedbackValue,
    MessageFeedback,
    ModelFeedbackStats,
    PreferenceRow,
    parse_feedback_value,
)

#: Ceiling on one export. A dump is a download, not a stream of the whole
#: table: past this the operator should narrow the window instead.
EXPORT_ROW_LIMIT = 10000


def to_row(feedback: MessageFeedback) -> MessageFeedbackRow:
    return MessageFeedbackRow(
        id=feedback.id,
        message_id=feedback.message_id,
        session_id=feedback.session_id,
        visitor_hash=feedback.visitor_hash,
        value=feedback.value,
        created_at=feedback.created_at,
    )


def to_feedback(row: MessageFeedbackRow) -> MessageFeedback:
    return MessageFeedback(
        id=row.id,
        message_id=row.message_id,
        session_id=row.session_id,
        visitor_hash=row.visitor_hash,
        value=parse_feedback_value(row.value),
        created_at=row.created_at,
    )


class SqlAlchemyFeedbackRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_for_message(self, message_id: UUID) -> MessageFeedback | None:
        row = await self._row_for(message_id)
        return to_feedback(row) if row is not None else None

    async def _row_for(self, message_id: UUID) -> MessageFeedbackRow | None:
        stmt = select(MessageFeedbackRow).where(MessageFeedbackRow.message_id == message_id)
        return (await self._db.execute(stmt)).scalars().one_or_none()

    async def upsert(self, feedback: MessageFeedback) -> MessageFeedback:
        """Last write wins, in place.

        Updating rather than inserting keeps the row's identity stable, so a
        reader flipping their mind twice leaves one row with one id — which is
        what the unique constraint promises anyway.
        """
        existing = await self._row_for(feedback.message_id)
        if existing is None:
            self._db.add(to_row(feedback))
            await self._db.flush()
            return feedback

        existing.value = feedback.value
        existing.visitor_hash = feedback.visitor_hash
        existing.created_at = feedback.created_at
        await self._db.flush()
        return to_feedback(existing)

    async def values_for_session(self, session_id: UUID) -> dict[UUID, FeedbackValue]:
        """Every vote cast in one chat, keyed by message.

        One query for the whole thread rather than one per message: history is
        rendered in a single response, and ``session_id`` is denormalized onto
        the vote precisely so this never has to walk through ``messages``.
        """
        stmt = select(MessageFeedbackRow.message_id, MessageFeedbackRow.value).where(
            MessageFeedbackRow.session_id == session_id
        )
        rows = (await self._db.execute(stmt)).all()
        return {message_id: parse_feedback_value(value) for message_id, value in rows}

    async def stats_by_model(self, *, since: datetime) -> list[ModelFeedbackStats]:
        """Up/down counts per answering model, over votes cast since ``since``.

        Grouped by the model on the *message*, not on a trace: a vote is about
        the answer the reader saw, and the message row is the only place that
        is guaranteed to record who wrote it.
        """
        ups = func.count().filter(MessageFeedbackRow.value == "up")
        downs = func.count().filter(MessageFeedbackRow.value == "down")
        stmt = (
            select(MessageRow.model_id, ups.label("ups"), downs.label("downs"))
            .select_from(MessageFeedbackRow)
            .join(MessageRow, MessageRow.id == MessageFeedbackRow.message_id)
            .where(MessageFeedbackRow.created_at >= since, MessageRow.model_id.is_not(None))
            .group_by(MessageRow.model_id)
        )
        rows = (await self._db.execute(stmt)).all()
        return [
            ModelFeedbackStats(model_id=str(model_id), ups=int(up_count), downs=int(down_count))
            for model_id, up_count, down_count in rows
        ]

    async def export_rows(
        self, *, since: datetime, until: datetime, include_content: bool = False
    ) -> AsyncIterator[PreferenceRow]:
        """One dataset line per vote, oldest first, with the trace when there is one.

        The join to ``run_traces`` is an outer join because a vote can outlive
        the measurement: answers written before tracing existed, or while it
        was switched off, are still perfectly good preference data.
        """
        prior = aliased(MessageRow)
        # The prompt that produced the answer: the newest user turn in the same
        # session at or before it. Correlated so it is evaluated per answer.
        prompt = (
            select(prior.content)
            .where(
                prior.session_id == MessageRow.session_id,
                prior.role == str(MessageRole.USER),
                prior.created_at <= MessageRow.created_at,
                prior.id != MessageRow.id,
            )
            .order_by(prior.created_at.desc(), prior.id.desc())
            .limit(1)
            .correlate(MessageRow)
            .scalar_subquery()
        )
        stmt = (
            select(
                MessageFeedbackRow.message_id,
                MessageFeedbackRow.value,
                MessageFeedbackRow.created_at,
                MessageRow.model_id,
                MessageRow.content,
                prompt.label("prompt"),
                RunTraceRow.ttft_ms,
                RunTraceRow.total_ms,
                RunTraceRow.attempts,
            )
            .select_from(MessageFeedbackRow)
            .join(MessageRow, MessageRow.id == MessageFeedbackRow.message_id)
            .outerjoin(RunTraceRow, RunTraceRow.message_id == MessageFeedbackRow.message_id)
            .where(
                MessageFeedbackRow.created_at >= since,
                MessageFeedbackRow.created_at <= until,
            )
            .order_by(MessageFeedbackRow.created_at, MessageFeedbackRow.message_id)
            .limit(EXPORT_ROW_LIMIT)
        )
        for row in (await self._db.execute(stmt)).all():
            yield PreferenceRow(
                message_id=row.message_id,
                model_id=row.model_id,
                feedback=parse_feedback_value(row.value),
                created_at=row.created_at,
                ttft_ms=row.ttft_ms,
                total_ms=row.total_ms,
                attempts=[attempt_from_json(a) for a in row.attempts or []],
                # Content is dropped here, at the source, rather than filtered
                # later: a row that never carries the text cannot leak it.
                prompt=row.prompt if include_content else None,
                answer=row.content if include_content else None,
            )
