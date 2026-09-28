"""In-process guest MCP registry keyed by authenticated user and server id."""

from __future__ import annotations

import asyncio
from uuid import UUID

from app.domain.guest_mcp import GuestMcpRecord


class InMemoryGuestMcpRegistry:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._store: dict[tuple[UUID, UUID], GuestMcpRecord] = {}

    async def list(self, owner_id: UUID) -> tuple[GuestMcpRecord, ...]:
        async with self._lock:
            return tuple(rec for (oid, _), rec in self._store.items() if oid == owner_id)

    async def put(self, owner_id: UUID, record: GuestMcpRecord) -> None:
        async with self._lock:
            self._store[(owner_id, record.server.id)] = record

    async def get(self, owner_id: UUID, server_id: UUID) -> GuestMcpRecord | None:
        async with self._lock:
            return self._store.get((owner_id, server_id))

    async def delete(self, owner_id: UUID, server_id: UUID) -> None:
        async with self._lock:
            self._store.pop((owner_id, server_id), None)
