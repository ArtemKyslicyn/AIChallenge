"""Session, history, chat-stream, and replay routes."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.adapters.api.schemas import (
    CreateSessionRequest,
    MessageResponse,
    SendMessageRequest,
    SessionCreatedResponse,
    SessionResponse,
    SessionSummaryResponse,
)
from app.adapters.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, format_frame, to_sse
from app.adapters.persistence.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)
from app.application.chat import ReplyDraft, interrupted_answer, send_user_message_and_stream
from app.application.sessions import create_session, list_visitor_sessions
from app.core.deps import (
    AuthorizedSession,
    Container,
    DbSession,
    SessionToken,
    VisitorHash,
    close_quietly,
    get_container,
    resolve_visitor_identity,
    run_shielded,
    utcnow,
    visitor_id_header,
)
from app.domain.entities import Message, MessageRole, Session, SessionStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["sessions"])


async def _write_interrupted(container: Container, draft: ReplyDraft) -> None:
    """Save a cut-off answer using a session of its own.

    A fresh session matters as much as the shielding: the request's session is
    being torn down at this point, and writing through it would race that.
    """
    assert draft.message_id is not None
    async with container.sessionmaker() as db:
        await SqlAlchemyMessageRepository(db).update_content(
            draft.message_id, interrupted_answer(draft), draft.model_id
        )
        await db.commit()
    logger.info(
        "saved interrupted reply message_id=%s model_id=%s", draft.message_id, draft.model_id
    )


async def _rescue_unsaved(container: Container, draft: ReplyDraft) -> None:
    """Persist whatever arrived when the reader hangs up mid-answer.

    The use case cannot do this itself: when the client disconnects, uvicorn
    cancels the request task, and the await inside its ``finally`` is cancelled
    with it — which used to leave the assistant row empty with a null model_id.
    The write therefore runs in a task of its own, shielded from that
    cancellation.
    """
    if draft.finished or draft.message_id is None or not draft.chunks:
        return

    await run_shielded(_write_interrupted(container, draft))


def _to_message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        role=str(message.role),
        content=message.content,
        model_id=message.model_id,
        created_at=message.created_at,
    )


@router.post("", response_model=SessionCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create(
    payload: CreateSessionRequest,
    request: Request,
    db: DbSession,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)],
) -> SessionCreatedResponse:
    container = get_container(request)
    identity = resolve_visitor_identity(request, client_visitor_id)
    visitor_key, ip_digest = identity if identity else (None, None)
    session = await create_session(
        sessions=SqlAlchemySessionRepository(db),
        scenarios=container.scenarios,
        scenario_id=payload.scenario_id,
        visitor_hash=visitor_key,
        ip_hash=ip_digest,
        now=utcnow,
    )
    await db.commit()
    # The only response that ever carries the token.
    return SessionCreatedResponse(id=session.id, access_token=session.access_token)


@router.get("/history", response_model=list[SessionSummaryResponse])
async def list_chat_history(
    visitor_hash: VisitorHash,
    db: DbSession,
) -> list[SessionSummaryResponse]:
    rows = await list_visitor_sessions(
        sessions=SqlAlchemySessionRepository(db),
        visitor_hash=visitor_hash,
    )
    return [
        SessionSummaryResponse(
            id=row.id,
            title=row.title,
            created_at=row.created_at,
            message_count=row.message_count,
        )
        for row in rows
    ]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session: AuthorizedSession) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        scenario_id=session.scenario_id,
        status=str(session.status),
        created_at=session.created_at,
        title=session.title,
    )


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def list_messages(
    session: AuthorizedSession,
    db: DbSession,
) -> list[MessageResponse]:
    rows = await SqlAlchemyMessageRepository(db).list_for_session(session.id)
    return [_to_message_response(row) for row in rows]


@router.post("/{session_id}/messages")
async def send_message(
    payload: SendMessageRequest,
    request: Request,
    session: AuthorizedSession,
    token: SessionToken,
) -> StreamingResponse:
    container = get_container(request)
    _reject_before_streaming(container, session, payload.content)

    draft = ReplyDraft()

    async def frames() -> AsyncIterator[str]:
        # The session is opened and closed by hand rather than with `async
        # with`: on a client disconnect the context manager's exit is cancelled
        # too, so the close has to be shielded like the rescue write.
        db = container.sessionmaker()
        try:
            events = send_user_message_and_stream(
                session_id=session.id,
                access_token=token,
                content=payload.content,
                preferred_model=payload.model,
                sessions=SqlAlchemySessionRepository(db),
                messages=SqlAlchemyMessageRepository(db),
                scenarios=container.scenarios,
                router=container.router,
                uow=db,
                now=utcnow,
                max_message_chars=container.settings.max_message_chars,
                max_history_messages=container.settings.max_history_messages,
                draft=draft,
            )
            async for frame in to_sse(events):
                yield frame
        finally:
            await _rescue_unsaved(container, draft)
            await close_quietly(db)

    return StreamingResponse(frames(), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)


def _reject_before_streaming(container: Container, session: Session, content: str) -> None:
    """Fail with a real status code instead of a 200 that carries an error.

    Once StreamingResponse starts, the status line is already on the wire.
    """
    if session.status is not SessionStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Сессия закрыта.")
    if not content.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Сообщение не может быть пустым."
        )
    limit = container.settings.max_message_chars
    if len(content) > limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Сообщение длиннее лимита в {limit} символов.",
        )


@router.get("/{session_id}/stream")
async def replay_message(
    message_id: UUID,
    session: AuthorizedSession,
    db: DbSession,
) -> StreamingResponse:
    """Replay a stored assistant message using the chat event shape.

    This is not a live resume: an answer still being generated returns 404.
    """
    message = await SqlAlchemyMessageRepository(db).get(message_id)
    if (
        message is None
        or message.session_id != session.id
        or message.role is not MessageRole.ASSISTANT
        or message.model_id is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Нечего воспроизвести.")

    frames = [
        format_frame("model", {"model_id": message.model_id}),
        format_frame("token", {"text": message.content}),
        format_frame(
            "message_end",
            {
                "message_id": str(message.id),
                "content": message.content,
                "model_id": message.model_id,
            },
        ),
    ]

    async def replay() -> AsyncIterator[str]:
        for frame in frames:
            yield frame

    return StreamingResponse(replay(), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)
