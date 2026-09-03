"""The chat use case writes exactly one measured row per finished turn."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import UUID

from fakes import (
    DEFAULT_SCENARIO,
    IdFactory,
    InMemoryMessageRepository,
    InMemoryRunTraceRepository,
    InMemoryScenarioRepository,
    InMemorySessionRepository,
    RecordingUnitOfWork,
    fixed_now,
)

from app.adapters.llm.fake import FakeLLMProvider, FlakyLLMProvider
from app.adapters.llm.router import ModelRouter
from app.application.chat import ChatEvent, send_user_message_and_stream
from app.domain.entities import Session, SessionStatus
from app.domain.tracing import (
    STATUS_ABORTED,
    STATUS_ERROR,
    STATUS_EXHAUSTED,
    STATUS_OK,
    RunTrace,
)

SESSION_ID = UUID(int=7)
TOKEN = "secret-token"
VISITOR = "visitor-hash"


@dataclass
class Ctx:
    messages: InMemoryMessageRepository
    traces: InMemoryRunTraceRepository | None
    uow: RecordingUnitOfWork
    router: ModelRouter
    cost_proxy: dict[str, float]
    sessions: InMemorySessionRepository
    scenarios: InMemoryScenarioRepository

    def stream(self, content: str = "hello") -> AsyncIterator[ChatEvent]:
        return send_user_message_and_stream(
            session_id=SESSION_ID,
            access_token=TOKEN,
            content=content,
            sessions=self.sessions,
            messages=self.messages,
            scenarios=self.scenarios,
            router=self.router,
            uow=self.uow,
            now=fixed_now,
            max_message_chars=100,
            max_history_messages=40,
            id_factory=IdFactory(),
            traces=self.traces,
            cost_proxy=self.cost_proxy,
        )

    async def drain(self, content: str = "hello") -> None:
        async for _ in self.stream(content):
            pass

    def only_trace(self) -> RunTrace:
        assert self.traces is not None
        assert len(self.traces.saved) == 1
        return self.traces.saved[0]


async def make_ctx(
    provider: object | None = None,
    *,
    chain: list[str] | None = None,
    traces: InMemoryRunTraceRepository | None = None,
    cost_proxy: dict[str, float] | None = None,
) -> Ctx:
    sessions = InMemorySessionRepository()
    await sessions.create(
        Session(
            id=SESSION_ID,
            access_token=TOKEN,
            scenario_id="default",
            status=SessionStatus.ACTIVE,
            created_at=fixed_now(),
            visitor_hash=VISITOR,
        )
    )
    return Ctx(
        sessions=sessions,
        messages=InMemoryMessageRepository(),
        scenarios=InMemoryScenarioRepository(DEFAULT_SCENARIO),
        traces=traces if traces is not None else InMemoryRunTraceRepository(),
        uow=RecordingUnitOfWork(),
        router=ModelRouter(
            provider or FakeLLMProvider(text="one two"),  # type: ignore[arg-type]
            chain or ["model-a"],
        ),
        cost_proxy=cost_proxy or {},
    )


async def test_a_finished_turn_is_measured_once() -> None:
    ctx = await make_ctx(cost_proxy={"model-a": 2.5})
    await ctx.drain()

    trace = ctx.only_trace()
    assert trace.session_id == SESSION_ID
    assert trace.message_id == ctx.messages.order[1]
    assert trace.status == STATUS_OK
    assert trace.resolved_model_id == "model-a"
    assert trace.preferred_model == "auto"
    assert trace.visitor_hash == VISITOR
    assert trace.cost_proxy == 2.5
    assert trace.token_count_est == len("one two") // 4
    assert trace.ttft_ms is not None and trace.ttft_ms >= 0
    assert trace.total_ms is not None and trace.total_ms >= 0
    assert trace.tool_rounds == 0
    assert trace.tool_ok is None


async def test_an_unpriced_model_has_no_cost_rather_than_a_default_one() -> None:
    ctx = await make_ctx(cost_proxy={"other-model": 2.5})
    await ctx.drain()
    assert ctx.only_trace().cost_proxy is None


async def test_the_journal_names_every_model_the_router_burned() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    ctx = await make_ctx(provider, chain=["model-a", "model-b"])
    await ctx.drain()

    trace = ctx.only_trace()
    assert [(a.model_id, a.ok) for a in trace.attempts] == [("model-a", False), ("model-b", True)]
    assert trace.resolved_model_id == "model-b"


async def test_an_exhausted_chain_is_recorded_without_a_model() -> None:
    provider = FlakyLLMProvider(fail_models={"model-a", "model-b"}, fail_status=429)
    ctx = await make_ctx(provider, chain=["model-a", "model-b"])
    await ctx.drain()

    trace = ctx.only_trace()
    assert trace.status == STATUS_EXHAUSTED
    assert trace.resolved_model_id is None
    assert [a.model_id for a in trace.attempts] == ["model-a", "model-b"]


async def test_a_cut_off_answer_is_recorded_as_aborted() -> None:
    provider = FlakyLLMProvider(fail_mid_stream={"model-a"}, partial_text="he", ok_text="hi")
    ctx = await make_ctx(provider, chain=["model-a", "model-b"])
    await ctx.drain()

    trace = ctx.only_trace()
    assert trace.status == STATUS_ABORTED
    assert trace.resolved_model_id == "model-a"
    assert trace.ttft_ms is not None


async def test_an_empty_answer_is_recorded_as_an_error() -> None:
    # A model that streams nothing at all and does not even fail.
    ctx = await make_ctx(FakeLLMProvider(text=""), chain=["model-a"])
    await ctx.drain()

    trace = ctx.only_trace()
    assert trace.status == STATUS_ERROR
    assert trace.token_count_est is None


async def test_a_failing_trace_write_never_breaks_the_answer() -> None:
    ctx = await make_ctx(traces=InMemoryRunTraceRepository(fail=True))
    events = [e async for e in ctx.stream()]

    # The reader still gets the whole answer, and the assistant row is intact.
    assert type(events[-1]).__name__ == "MessageEndEvent"
    assert ctx.messages.rows[ctx.messages.order[1]].content == "one two"
    # The broken transaction is rolled back, or the next commit inherits it.
    assert ctx.uow.rollbacks == 1


async def test_tracing_can_be_switched_off_entirely() -> None:
    ctx = await make_ctx(traces=None)
    await ctx.drain()
    assert ctx.messages.rows[ctx.messages.order[1]].content == "one two"


async def test_a_reader_that_hangs_up_writes_no_trace() -> None:
    # Documented v1 compromise (prep decision D3): the disconnect rescue path
    # saves the partial message, not a trace.
    ctx = await make_ctx()
    stream = ctx.stream()
    await anext(stream)
    await stream.aclose()

    assert ctx.traces is not None
    assert ctx.traces.saved == []
