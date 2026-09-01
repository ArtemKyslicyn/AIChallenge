"""Ports the application layer depends on. Adapters implement them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol
from uuid import UUID

from app.domain.entities import (
    AUTO_MODEL,
    ChatMessage,
    CompletionResult,
    Message,
    Scenario,
    Session,
    SessionSummary,
    TokenChunk,
)
from app.domain.generation import GenerationParams


class SessionRepository(Protocol):
    async def create(self, session: Session) -> Session: ...

    async def get(self, session_id: UUID) -> Session | None: ...

    async def list_for_visitor(
        self, visitor_hash: str, *, limit: int = 50
    ) -> list[SessionSummary]: ...

    async def set_title_if_empty(self, session_id: UUID, title: str) -> None: ...


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
    def stream_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]: ...

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        model: str,
        *,
        generation: GenerationParams | None = None,
    ) -> CompletionResult: ...


class ChatRouter(Protocol):
    """A model chain that resolves which model actually answers.

    Implemented by the ModelRouter adapter; declared here so use cases depend
    on the port rather than on the adapter.
    """

    def stream_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
    ) -> AsyncIterator[TokenChunk]: ...

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
    ) -> CompletionResult: ...


class UnitOfWork(Protocol):
    """Transaction boundary owned by the caller, not by the repositories.

    The chat use case needs explicit checkpoints: the user message must be
    durable before the stream starts, and the assistant row must be durable
    after it ends — including when the client disconnects halfway.
    """

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
