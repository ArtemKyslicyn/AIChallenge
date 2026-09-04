"""Thumbs on one assistant message.

Lives on ``/messages`` rather than under a session, because the browser knows
the message id at the moment the answer ends and nothing else. Ownership is
still proven with the session token — see :mod:`app.application.feedback`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.application.feedback import NOT_FOUND, retract_feedback, submit_feedback
from app.core.deps import (
    Feedback,
    Messages,
    Sessions,
    SessionToken,
    Uow,
    get_container,
    resolve_visitor_identity,
    spawn_detached,
    utcnow,
    visitor_id_header,
)
from app.domain.analytics import AnalyticsEvent
from app.domain.feedback import FeedbackValue

router = APIRouter(prefix="/messages", tags=["feedback"])


class FeedbackRequest(BaseModel):
    #: Two values, validated by the schema — the domain never sees a third.
    value: FeedbackValue


class FeedbackResponse(BaseModel):
    message_id: UUID
    value: FeedbackValue


def _parsed_id(message_id: str) -> UUID:
    """Parse in the adapter so a malformed id is the same 404 as an unknown one.

    A 422 would confirm that well-formed ids are the ones worth guessing.
    """
    try:
        return UUID(message_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=NOT_FOUND) from None


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
    """Record "helpful" or "not helpful" for one answer; last vote wins."""
    parsed = _parsed_id(message_id)
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
    distinct = (identity[0] if identity else "") or "anonymous"
    container = get_container(request)
    spawn_detached(
        container.analytics.capture(
            [
                AnalyticsEvent(
                    name="feedback_set",
                    distinct_id=distinct,
                    properties={
                        "message_id": str(stored.message_id),
                        "value": stored.value,
                    },
                )
            ]
        )
    )
    return FeedbackResponse(message_id=stored.message_id, value=stored.value)


@router.delete(
    "/{message_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def unrate_message(
    message_id: str,
    token: SessionToken,
    messages: Messages,
    sessions: Sessions,
    feedback: Feedback,
    uow: Uow,
) -> Response:
    """Take the vote back — the pressed thumb, pressed again.

    ``aria-pressed`` on the buttons promises a control that can be un-pressed,
    so there has to be a way to say "no opinion" after saying something else.

    Idempotent, and therefore ``204`` even when there was nothing to remove: the
    caller asked for a message with no vote on it and that is what they have.
    A 404 there would push the client into tracking whether its own optimistic
    retraction had already landed. No body for the same reason — there is no
    value left to report, and ``null`` would only invite a client to read it.

    Authorization is the POST's, to the letter (prep D6): a wrong token, an
    unknown message and someone else's session are one indistinguishable 404.
    No visitor header is read — the vote being removed is identified by the
    message alone, and the hash it carried was never a credential.
    """
    await retract_feedback(
        message_id=_parsed_id(message_id),
        access_token=token,
        messages=messages,
        sessions=sessions,
        feedback=feedback,
        uow=uow,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
