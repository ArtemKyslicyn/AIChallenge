"""Session, history, chat-stream, and replay routes."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.adapters.api.schemas import (
    CreateSessionRequest,
    MessageResponse,
    SendMessageRequest,
    SessionCreatedResponse,
    SessionResponse,
)
from app.adapters.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, format_frame, to_sse
from app.adapters.persistence.repositories import (
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)
from app.application.chat import send_user_message_and_stream
from app.application.sessions import create_session
from app.core.deps import (
    AuthorizedSession,
    Container,
    DbSession,
    SessionToken,
    get_container,
    utcnow,
)
from app.domain.entities import Message, MessageRole, Session, SessionStatus

router = APIRouter(prefix="/sessions", tags=["sessions"])


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
) -> SessionCreatedResponse:
    container = get_container(request)
    session = await create_session(
        sessions=SqlAlchemySessionRepository(db),
        scenarios=container.scenarios,
        scenario_id=payload.scenario_id,
        now=utcnow,
    )
    await db.commit()
    # The only response that ever carries the token.
    return SessionCreatedResponse(id=session.id, access_token=session.access_token)


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session: AuthorizedSession) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        scenario_id=session.scenario_id,
        status=str(session.status),
        created_at=session.created_at,
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

    async def frames() -> AsyncIterator[str]:
        # The DB session is owned by this generator rather than injected.
        # A mutation test showed the Depends form also working on this FastAPI
        # version, so this is not a bug fix — it makes the lifetime explicit
        # and independent of when yield-dependency teardown runs, which has
        # changed between FastAPI versions. The final update_content happens
        # after the last token, well past the endpoint's own frame.
        async with container.sessionmaker() as db:
            events = send_user_message_and_stream(
                session_id=session.id,
                access_token=token,
                content=payload.content,
                sessions=SqlAlchemySessionRepository(db),
                messages=SqlAlchemyMessageRepository(db),
                scenarios=container.scenarios,
                router=container.router,
                uow=db,
                now=utcnow,
                max_message_chars=container.settings.max_message_chars,
                max_history_messages=container.settings.max_history_messages,
            )
            async for frame in to_sse(events):
                yield frame

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
