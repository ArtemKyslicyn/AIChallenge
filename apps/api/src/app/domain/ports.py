"""Ports the application layer depends on. Adapters implement them."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol
from uuid import UUID

from app.domain.cascade import CascadeSummary
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
from app.domain.feedback import MessageFeedback, ModelFeedbackStats, PreferenceRow
from app.domain.generation import GenerationParams
from app.domain.media import MediaArtifact, StoredMedia
from app.domain.tracing import AttemptRecord, ModelAggregate, RunTrace


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
        tools: list[dict[str, object]] | None = None,
    ) -> CompletionResult: ...


class ChatRouter(Protocol):
    """A model chain that resolves which model actually answers.

    Implemented by the ModelRouter adapter; declared here so use cases depend
    on the port rather than on the adapter.
    """

    #: ``attempts`` is the caller's per-request journal. It is a parameter and
    #: not router state because one router instance serves every concurrent
    #: stream in the process; ``None`` means "this caller is not measuring".
    def stream_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
        attempts: list[AttemptRecord] | None = None,
    ) -> AsyncIterator[TokenChunk]: ...

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = AUTO_MODEL,
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
        attempts: list[AttemptRecord] | None = None,
    ) -> CompletionResult: ...


class RunTraceRepository(Protocol):
    """Persistence for run traces, plus the one read model the Lab needs."""

    async def save(self, trace: RunTrace) -> None: ...

    #: Attach a judge's verdict to an already-written trace. False when there
    #: was no row to attach it to, which is a normal outcome, not a failure.
    async def set_quality(
        self, message_id: UUID, *, score: float, judge_model_id: str
    ) -> bool: ...

    async def list_for_session(self, session_id: UUID) -> list[RunTrace]: ...

    #: message_id → cascade stage, for the messages of one chat that have one.
    #: Absent means ``off``; see the implementation for why it is not returned.
    async def stages_for_session(self, session_id: UUID) -> dict[UUID, str]: ...

    async def aggregate(self, *, since: datetime, until: datetime) -> list[ModelAggregate]: ...

    #: ``None`` when the cascade never ran in this window — the Lab draws the
    #: escalation line only when there is something to draw.
    async def cascade_summary(
        self, *, since: datetime, until: datetime
    ) -> CascadeSummary | None: ...


class FeedbackRepository(Protocol):
    """Persistence for votes, plus the two read models built on top of them."""

    async def upsert(self, feedback: MessageFeedback) -> MessageFeedback: ...

    async def get_for_message(self, message_id: UUID) -> MessageFeedback | None: ...

    #: Take one vote back. Answers whether a row went away, so the caller can
    #: tell a retraction from a no-op — both are success at the API edge.
    async def delete_for_message(self, message_id: UUID) -> bool: ...

    async def stats_by_model(self, *, since: datetime) -> list[ModelFeedbackStats]: ...

    #: Declared as a plain ``def`` for the same reason as ``stream_chat``: an
    #: ``async def`` generator satisfies this, an async method would not.
    def export_rows(
        self, *, since: datetime, until: datetime, include_content: bool = False
    ) -> AsyncIterator[PreferenceRow]: ...


class MediaGenerator(Protocol):
    async def generate_image(
        self,
        prompt: str,
        *,
        model: str = "flux",
        width: int = 1024,
        height: int = 1024,
    ) -> MediaArtifact: ...

    async def generate_video(self, prompt: str) -> MediaArtifact: ...


class MediaStore(Protocol):
    async def save(self, artifact: MediaArtifact) -> StoredMedia: ...

    async def get(self, media_id: object) -> tuple[bytes, str] | None: ...


class UnitOfWork(Protocol):
    """Transaction boundary owned by the caller, not by the repositories.

    The chat use case needs explicit checkpoints: the user message must be
    durable before the stream starts, and the assistant row must be durable
    after it ends — including when the client disconnects halfway.
    """

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
