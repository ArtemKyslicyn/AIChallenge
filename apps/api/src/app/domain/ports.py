"""Ports the application layer depends on. Adapters implement them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from app.domain.entities import (
    ChatMessage,
    CompletionResult,
    Message,
    Scenario,
    Session,
    TokenChunk,
)


class SessionRepository(Protocol):
    async def create(self, session: Session) -> Session: ...

    async def get(self, session_id: UUID) -> Session | None: ...


class MessageRepository(Protocol):
    async def add(self, message: Message) -> Message: ...

    async def list_for_session(self, session_id: UUID) -> list[Message]: ...

    async def update_content(
        self, message_id: UUID, content: str, model_id: str | None
    ) -> Message: ...

    async def get(self, message_id: UUID) -> Message | None: ...


class ScenarioRepository(Protocol):
    async def get(self, scenario_id: str) -> Scenario | None: ...

    async def get_default(self) -> Scenario: ...


class LLMProvider(Protocol):
    #: Declared as a plain ``def`` returning an ``AsyncIterator`` so that an
    #: ``async def`` generator satisfies the protocol. ``async def`` here would
    #: instead require a coroutine that *returns* an iterator.
    def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[TokenChunk]: ...

    async def complete_chat(self, messages: list[ChatMessage], model: str) -> CompletionResult: ...
