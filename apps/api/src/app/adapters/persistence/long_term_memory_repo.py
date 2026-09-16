"""SQLAlchemy adapter for visitor long-term agent memory."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import AgentLongTermMemoryRow
from app.domain.agent_memory import LongTermMemory


class SqlAlchemyLongTermMemoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, client_visitor_id: str) -> LongTermMemory:
        owner = (client_visitor_id or "").strip().lower()
        if not owner:
            return LongTermMemory()
        row = await self._db.get(AgentLongTermMemoryRow, owner)
        if row is None:
            return LongTermMemory()
        return LongTermMemory.from_mapping(
            {
                "profile": row.profile or {},
                "decisions": row.decisions or [],
                "knowledge": row.knowledge or {},
            }
        )

    async def save(self, client_visitor_id: str, memory: LongTermMemory) -> LongTermMemory:
        owner = (client_visitor_id or "").strip().lower()
        if not owner:
            raise ValueError("client_visitor_id required")
        now = datetime.now(UTC)
        row = await self._db.get(AgentLongTermMemoryRow, owner)
        payload = memory.to_dict()
        if row is None:
            row = AgentLongTermMemoryRow(
                client_visitor_id=owner,
                profile=dict(payload["profile"]),
                decisions=list(payload["decisions"]),
                knowledge=dict(payload["knowledge"]),
                updated_at=now,
            )
            self._db.add(row)
        else:
            row.profile = dict(payload["profile"])
            row.decisions = list(payload["decisions"])
            row.knowledge = dict(payload["knowledge"])
            row.updated_at = now
        await self._db.flush()
        return memory

    async def delete(self, client_visitor_id: str) -> None:
        owner = (client_visitor_id or "").strip().lower()
        if not owner:
            return
        row = await self._db.get(AgentLongTermMemoryRow, owner)
        if row is not None:
            await self._db.delete(row)
            await self._db.flush()
