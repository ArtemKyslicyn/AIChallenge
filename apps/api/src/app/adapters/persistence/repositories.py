"""Repository adapters mapping rows to domain entities.

Repositories flush but never commit: the caller owns the transaction. That
matters for SSE, where the assistant row is written once at the start and
updated again after the stream ends.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import MessageRow, SessionRow
from app.domain.entities import Message, MessageRole, Session, SessionStatus
from app.domain.errors import MessageNotFoundError


def _to_session(row: SessionRow) -> Session:
    return Session(
        id=row.id,
        access_token=row.access_token,
        scenario_id=row.scenario_id,
        status=SessionStatus(row.status),
        created_at=row.created_at,
        user_id=row.user_id,
    )


def _to_message(row: MessageRow) -> Message:
    return Message(
        id=row.id,
        session_id=row.session_id,
        role=MessageRole(row.role),
        content=row.content,
        created_at=row.created_at,
        model_id=row.model_id,
    )


class SqlAlchemySessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, session: Session) -> Session:
        row = SessionRow(
            id=session.id,
            access_token=session.access_token,
            scenario_id=session.scenario_id,
            status=str(session.status),
            created_at=session.created_at,
            user_id=session.user_id,
        )
        self._db.add(row)
        await self._db.flush()
        return _to_session(row)

    async def get(self, session_id: UUID) -> Session | None:
        row = await self._db.get(SessionRow, session_id)
        return _to_session(row) if row is not None else None


class SqlAlchemyMessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, message: Message) -> Message:
        row = MessageRow(
            id=message.id,
            session_id=message.session_id,
            role=str(message.role),
            content=message.content,
            model_id=message.model_id,
            created_at=message.created_at,
        )
        self._db.add(row)
        await self._db.flush()
        return _to_message(row)

    async def list_for_session(self, session_id: UUID) -> list[Message]:
        stmt = (
            select(MessageRow)
            .where(MessageRow.session_id == session_id)
            .order_by(MessageRow.created_at, MessageRow.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [_to_message(row) for row in rows]

    async def update_content(self, message_id: UUID, content: str, model_id: str | None) -> Message:
        row = await self._db.get(MessageRow, message_id)
        if row is None:
            raise MessageNotFoundError(f"Сообщение {message_id} не найдено.")
        row.content = content
        row.model_id = model_id
        await self._db.flush()
        return _to_message(row)

    async def get(self, message_id: UUID) -> Message | None:
        row = await self._db.get(MessageRow, message_id)
        return _to_message(row) if row is not None else None
