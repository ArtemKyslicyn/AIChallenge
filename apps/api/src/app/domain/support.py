"""Support desk: synthetic tickets + FAQ-backed answers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SupportTicket:
    id: str
    status: str
    symptom: str
    notes: str = ""


class TicketStore(Protocol):
    async def get(self, ticket_id: str) -> SupportTicket | None: ...

    async def search(self, query: str, *, limit: int = 10) -> tuple[SupportTicket, ...]: ...

    async def create(self, *, symptom: str, notes: str = "") -> SupportTicket: ...


@dataclass(frozen=True, slots=True)
class SupportAnswer:
    body: str
    ticket: SupportTicket | None
    faq_sources: tuple[str, ...]
    escalate: bool
    model_id: str
