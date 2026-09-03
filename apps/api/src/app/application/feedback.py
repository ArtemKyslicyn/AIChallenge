"""Submitting a vote, and shaping one export line.

The whole use case is an authorization check followed by an upsert — but the
check is the interesting half, because a message id is the only thing the
client sends and it must not become a way to read or rate someone else's chat.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from app.application.sessions import authorize_session
from app.domain.entities import MessageRole
from app.domain.errors import FeedbackTargetError, MessageNotFoundError, SessionNotFoundError
from app.domain.feedback import FeedbackValue, MessageFeedback, PreferenceRow
from app.domain.ports import (
    FeedbackRepository,
    MessageRepository,
    SessionRepository,
    UnitOfWork,
)

#: One sentence for three different failures — an unknown message, a message in
#: someone else's session, and a wrong token all say exactly this. Telling them
#: apart would turn the endpoint into a way to probe which messages exist.
NOT_FOUND = "Сообщение не найдено."


async def submit_feedback(
    *,
    message_id: UUID,
    access_token: str | None,
    value: FeedbackValue,
    visitor_hash: str | None = None,
    messages: MessageRepository,
    sessions: SessionRepository,
    feedback: FeedbackRepository,
    uow: UnitOfWork,
    now: Callable[[], datetime],
    id_factory: Callable[[], UUID] = uuid4,
) -> MessageFeedback:
    """Record one reader's verdict on one assistant answer.

    Ownership is proven the long way round: the message names its session, and
    the caller must hold that session's token. There is no shortcut through the
    visitor hash — that is an analytics label, not a credential.
    """
    message = await messages.get(message_id)
    if message is None:
        raise MessageNotFoundError(NOT_FOUND)

    try:
        await authorize_session(
            sessions=sessions, session_id=message.session_id, access_token=access_token
        )
    except SessionNotFoundError:
        # Collapsed into the same 404, on purpose. See NOT_FOUND.
        raise MessageNotFoundError(NOT_FOUND) from None

    if message.role is not MessageRole.ASSISTANT:
        # A different failure entirely: the caller proved ownership, they just
        # pointed at their own question instead of the answer to it.
        raise FeedbackTargetError("Оценить можно только ответ модели.")

    stored = await feedback.upsert(
        MessageFeedback(
            id=id_factory(),
            message_id=message.id,
            session_id=message.session_id,
            visitor_hash=visitor_hash,
            value=value,
            created_at=now(),
        )
    )
    await uow.commit()
    return stored


def preference_row_json(row: PreferenceRow) -> dict[str, Any]:
    """One JSONL line, with the content keys present only when they are filled.

    Absent rather than null: a consumer reading a default export should not
    have to know that a ``prompt`` field could have existed.
    """
    payload: dict[str, Any] = {
        "message_id": str(row.message_id),
        "model_id": row.model_id,
        "feedback": row.feedback,
        "ttft_ms": row.ttft_ms,
        "total_ms": row.total_ms,
        "attempts": [
            {
                "model_id": attempt.model_id,
                "ok": attempt.ok,
                "reason": attempt.reason,
                "ttft_ms": attempt.ttft_ms,
                "error_kind": attempt.error_kind,
            }
            for attempt in row.attempts
        ],
        "created_at": row.created_at.isoformat(),
    }
    if row.prompt is not None:
        payload["prompt"] = row.prompt
    if row.answer is not None:
        payload["answer"] = row.answer
    return payload
