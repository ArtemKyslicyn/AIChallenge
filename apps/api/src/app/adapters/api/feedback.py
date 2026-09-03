"""Thumbs on one assistant message.

Lives on ``/messages`` rather than under a session, because the browser knows
the message id at the moment the answer ends and nothing else. Ownership is
still proven with the session token — see :mod:`app.application.feedback`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.application.feedback import NOT_FOUND, submit_feedback
from app.core.deps import (
    Feedback,
    Messages,
    Sessions,
    SessionToken,
    Uow,
    resolve_visitor_identity,
    utcnow,
    visitor_id_header,
)
from app.domain.feedback import FeedbackValue

router = APIRouter(prefix="/messages", tags=["feedback"])


class FeedbackRequest(BaseModel):
    #: Two values, validated by the schema — the domain never sees a third.
    value: FeedbackValue


class FeedbackResponse(BaseModel):
    message_id: UUID
    value: FeedbackValue


@router.post("/{message_id}/feedback", response_model=FeedbackResponse)
async def rate_message(
    message_id: str,
    payload: FeedbackRequest,
    request: Request,
    token: SessionToken,
    messages: Messages,
    sessions: Sessions,
    feedback: Feedback,
    uow: Uow,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> FeedbackResponse:
    """Record "helpful" or "not helpful" for one answer; last vote wins.

    ``message_id`` is taken as a string and parsed here so that a malformed id
    is the same 404 as an unknown one — a 422 would confirm that well-formed
    ids are the ones worth guessing.
    """
    try:
        parsed = UUID(message_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND) from None

    identity = resolve_visitor_identity(request, client_visitor_id)
    stored = await submit_feedback(
        message_id=parsed,
        access_token=token,
        value=payload.value,
        visitor_hash=identity[0] if identity else None,
        messages=messages,
        sessions=sessions,
        feedback=feedback,
        uow=uow,
        now=utcnow,
    )
    return FeedbackResponse(message_id=stored.message_id, value=stored.value)
