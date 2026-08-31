from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from fakes import (
    DEFAULT_SCENARIO,
    FIXED_NOW,
    IdFactory,
    InMemoryMessageRepository,
    InMemoryScenarioRepository,
    InMemorySessionRepository,
    RecordingUnitOfWork,
    fixed_now,
)

from app.adapters.llm.fake import FakeLLMProvider, FlakyLLMProvider
from app.adapters.llm.router import ModelRouter
from app.application.chat import (
    ERROR_EMPTY,
    ERROR_NO_MODEL,
    INTERRUPTED_MARKER,
    ChatEvent,
    ErrorEvent,
    MessageEndEvent,
    ModelEvent,
    TokenEvent,
    send_user_message_and_stream,
)
from app.domain.entities import ChatMessage, Message, MessageRole, Session, SessionStatus
from app.domain.errors import MessageValidationError, SessionNotFoundError

SESSION_ID = UUID(int=7)
TOKEN = "secret-token"


class SpyProvider(FakeLLMProvider):
    """Records the turns the router hands to the provider."""

    def __init__(self, text: str = "one two") -> None:
        super().__init__(text=text)
        self.seen: list[ChatMessage] = []

    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator:
        self.seen = list(messages)
        async for chunk in super().stream_chat(messages, model):
            yield chunk


@dataclass
class Ctx:
    sessions: InMemorySessionRepository
    messages: InMemoryMessageRepository
    scenarios: InMemoryScenarioRepository
    uow: RecordingUnitOfWork
    router: ModelRouter

    def stream(
        self,
        content: str = "hello",
        access_token: str | None = TOKEN,
        max_message_chars: int = 100,
        max_history_messages: int = 40,
    ) -> AsyncIterator[ChatEvent]:
        return send_user_message_and_stream(
            session_id=SESSION_ID,
            access_token=access_token,
            content=content,
            sessions=self.sessions,
            messages=self.messages,
            scenarios=self.scenarios,
            router=self.router,
            uow=self.uow,
            now=fixed_now,
            max_message_chars=max_message_chars,
            max_history_messages=max_history_messages,
            id_factory=IdFactory(),
        )

    def assistant_row(self) -> Message:
        rows = [m for m in self.messages.rows.values() if m.role is MessageRole.ASSISTANT]
        assert len(rows) == 1
        return rows[0]


async def make_ctx(provider: object | None = None) -> Ctx:
    sessions = InMemorySessionRepository()
    await sessions.create(
        Session(
            id=SESSION_ID,
            access_token=TOKEN,
            scenario_id="default",
            status=SessionStatus.ACTIVE,
            created_at=FIXED_NOW,
        )
    )
    router = ModelRouter(
        provider or FakeLLMProvider(text="one two"),  # type: ignore[arg-type]
        ["model-a", "model-b"],
    )
    return Ctx(
        sessions=sessions,
        messages=InMemoryMessageRepository(),
        scenarios=InMemoryScenarioRepository(DEFAULT_SCENARIO),
        uow=RecordingUnitOfWork(),
        router=router,
    )


async def collect(events: AsyncIterator[ChatEvent]) -> list[ChatEvent]:
    return [event async for event in events]


async def test_event_order_and_single_model_attribution() -> None:
    ctx = await make_ctx()
    events = await collect(ctx.stream())

    assert isinstance(events[0], ModelEvent)
    assert all(isinstance(e, TokenEvent) for e in events[1:-1])
    end = events[-1]
    assert isinstance(end, MessageEndEvent)

    # Failover is pre-first-token only, so exactly one model event.
    assert sum(isinstance(e, ModelEvent) for e in events) == 1
    assert events[0].model_id == end.model_id == "model-a"
    assert end.content == "one two"


async def test_assistant_row_persists_content_and_model_id() -> None:
    ctx = await make_ctx()
    await collect(ctx.stream())

    row = ctx.assistant_row()
    assert row.content == "one two"
    assert row.model_id == "model-a"
    # One commit makes the user turn durable, one saves the finished answer.
    assert ctx.uow.commits == 2


async def test_user_message_is_persisted_before_the_provider_runs() -> None:
    ctx = await make_ctx()
    stream = ctx.stream(content="hello")
    await stream.__anext__()  # first model event: the provider has been reached

    user_rows = [m for m in ctx.messages.rows.values() if m.role is MessageRole.USER]
    assert [m.content for m in user_rows] == ["hello"]
    assert ctx.uow.commits >= 1
    await stream.aclose()


async def test_mid_stream_abort_saves_partial_answer_and_reports_error() -> None:
    provider = FlakyLLMProvider(fail_mid_stream={"model-a"}, partial_text="one two")
    ctx = await make_ctx(provider)
    events = await collect(ctx.stream())

    assert isinstance(events[-1], ErrorEvent)
    assert not any(isinstance(e, MessageEndEvent) for e in events)
    # No second model event: the router never switched to model-b.
    assert sum(isinstance(e, ModelEvent) for e in events) == 1

    row = ctx.assistant_row()
    assert row.content == "one two" + INTERRUPTED_MARKER
    assert row.model_id == "model-a"


async def test_exhausted_chain_reports_error_without_model_id() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a", "model-b"}, fail_status=429)
    ctx = await make_ctx(provider)
    events = await collect(ctx.stream())

    assert events == [ErrorEvent(message=ERROR_NO_MODEL)]
    row = ctx.assistant_row()
    assert row.content == ""
    assert row.model_id is None


async def test_empty_answer_reports_error() -> None:
    ctx = await make_ctx(FakeLLMProvider(text=""))
    events = await collect(ctx.stream())
    assert events == [ErrorEvent(message=ERROR_EMPTY)]


async def test_client_disconnect_still_persists_what_arrived() -> None:
    ctx = await make_ctx()
    stream = ctx.stream()

    seen: list[ChatEvent] = []
    async for event in stream:
        seen.append(event)
        if isinstance(event, TokenEvent):
            break
    await stream.aclose()  # what Starlette does when the client hangs up

    row = ctx.assistant_row()
    assert row.content == "one " + INTERRUPTED_MARKER
    assert row.model_id == "model-a"


async def test_history_sent_to_the_model_is_capped() -> None:
    provider = SpyProvider()
    ctx = await make_ctx(provider)
    for i in range(10):
        await ctx.messages.add(
            Message(
                id=UUID(int=100 + i),
                session_id=SESSION_ID,
                role=MessageRole.USER,
                content=f"old-{i}",
                created_at=FIXED_NOW,
            )
        )

    await collect(ctx.stream(content="newest", max_history_messages=4))

    assert provider.seen[0].role is MessageRole.SYSTEM
    assert len(provider.seen) == 5  # system prompt + 4 turns
    assert provider.seen[-1].content == "newest"
    assert "old-0" not in [m.content for m in provider.seen]


async def test_empty_message_is_rejected_before_any_write() -> None:
    ctx = await make_ctx()
    with pytest.raises(MessageValidationError):
        await collect(ctx.stream(content="   "))
    assert ctx.messages.rows == {}


async def test_oversized_message_is_rejected_before_any_write() -> None:
    ctx = await make_ctx()
    with pytest.raises(MessageValidationError):
        await collect(ctx.stream(content="x" * 101, max_message_chars=100))
    assert ctx.messages.rows == {}


async def test_wrong_token_is_rejected() -> None:
    ctx = await make_ctx()
    with pytest.raises(SessionNotFoundError):
        await collect(ctx.stream(access_token="nope"))
    assert ctx.messages.rows == {}
