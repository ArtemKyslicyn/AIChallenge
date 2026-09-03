"""The cascade decides before the first character, and stays invisible when off."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
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

from app.adapters.llm.heuristic_scorer import HeuristicAnswerScorer
from app.application.chat import (
    CascadeSettings,
    ChatEvent,
    MessageEndEvent,
    ModelEvent,
    TokenEvent,
    send_user_message_and_stream,
)
from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF, ScoreVerdict
from app.domain.entities import ChatMessage, CompletionResult, Session, SessionStatus, TokenChunk
from app.domain.errors import LLMExhaustedError
from app.domain.generation import GenerationParams
from app.domain.tracing import AttemptRecord

SESSION_ID = UUID(int=7)
TOKEN = "secret-token"

QUESTION = "Объясни, чем очередь отличается от стека."
GOOD_CHEAP = (
    "Очередь работает по принципу FIFO, а стек — по принципу LIFO. "
    "Это определяет, какой элемент извлекается первым."
)


class SpyRouter:
    """Records which surface the chat used, and for which model."""

    def __init__(
        self,
        *,
        cheap_text: str = GOOD_CHEAP,
        cheap_model_id: str = "cheap-1",
        stream_text: str = "сильный ответ",
        stream_model_id: str = "model-a",
        cheap_error: Exception | None = None,
    ) -> None:
        self.cheap_text = cheap_text
        self.cheap_model_id = cheap_model_id
        self.stream_text = stream_text
        self.stream_model_id = stream_model_id
        self.cheap_error = cheap_error
        self.completed: list[str] = []
        self.streamed: list[str] = []

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = "auto",
        *,
        generation: GenerationParams | None = None,
        tools: list[dict[str, object]] | None = None,
        attempts: list[AttemptRecord] | None = None,
    ) -> CompletionResult:
        self.completed.append(preferred_model)
        if self.cheap_error is not None:
            raise self.cheap_error
        if attempts is not None:
            attempts.append(AttemptRecord(model_id=self.cheap_model_id, ok=True, ttft_ms=5))
        return CompletionResult(content=self.cheap_text, model_id=self.cheap_model_id)

    async def stream_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = "auto",
        *,
        generation: GenerationParams | None = None,
        attempts: list[AttemptRecord] | None = None,
    ) -> AsyncIterator[TokenChunk]:
        self.streamed.append(preferred_model)
        if attempts is not None:
            attempts.append(AttemptRecord(model_id=self.stream_model_id, ok=True, ttft_ms=7))
        yield TokenChunk(text=self.stream_text, model_id=self.stream_model_id)


class StubScorer:
    def __init__(self, verdict: ScoreVerdict) -> None:
        self.verdict = verdict

    def score(self, question: str, answer: str) -> ScoreVerdict:
        return self.verdict


CASCADE_ON = CascadeSettings(
    enabled=True, cheap_models=["cheap-1"], timeout_seconds=5.0, max_question_chars=1200
)


@dataclass
class Ctx:
    messages: InMemoryMessageRepository
    traces: InMemoryRunTraceRepository
    uow: RecordingUnitOfWork
    router: SpyRouter
    sessions: InMemorySessionRepository
    scenarios: InMemoryScenarioRepository

    def stream(
        self,
        *,
        content: str = QUESTION,
        scorer: Any = None,
        cascade: CascadeSettings | None = None,
        preferred_model: str | None = None,
    ) -> AsyncIterator[ChatEvent]:
        return send_user_message_and_stream(
            session_id=SESSION_ID,
            access_token=TOKEN,
            content=content,
            preferred_model=preferred_model,
            sessions=self.sessions,
            messages=self.messages,
            scenarios=self.scenarios,
            router=self.router,  # type: ignore[arg-type]
            uow=self.uow,
            now=fixed_now,
            max_message_chars=8000,
            max_history_messages=40,
            id_factory=IdFactory(),
            traces=self.traces,
            scorer=scorer,
            cascade=cascade,
        )

    async def events(self, **kwargs: Any) -> list[ChatEvent]:
        return [e async for e in self.stream(**kwargs)]

    def only_trace(self) -> Any:
        assert len(self.traces.saved) == 1
        return self.traces.saved[0]


async def make_ctx(router: SpyRouter | None = None) -> Ctx:
    sessions = InMemorySessionRepository()
    await sessions.create(
        Session(
            id=SESSION_ID,
            access_token=TOKEN,
            scenario_id="default",
            status=SessionStatus.ACTIVE,
            created_at=fixed_now(),
        )
    )
    return Ctx(
        sessions=sessions,
        messages=InMemoryMessageRepository(),
        scenarios=InMemoryScenarioRepository(DEFAULT_SCENARIO),
        traces=InMemoryRunTraceRepository(),
        uow=RecordingUnitOfWork(),
        router=router or SpyRouter(),
    )


async def test_a_disabled_cascade_changes_nothing() -> None:
    ctx = await make_ctx()
    events = await ctx.events()

    assert ctx.router.completed == []
    assert ctx.router.streamed == ["auto"]
    assert [type(e).__name__ for e in events] == ["ModelEvent", "TokenEvent", "MessageEndEvent"]
    trace = ctx.only_trace()
    assert trace.cascade_stage == CASCADE_OFF
    assert trace.cheap_model_id is None
    assert trace.cheap_score is None


async def test_settings_present_but_switched_off_still_change_nothing() -> None:
    ctx = await make_ctx()
    off = CascadeSettings(
        enabled=False, cheap_models=["cheap-1"], timeout_seconds=5.0, max_question_chars=1200
    )
    await ctx.events(scorer=HeuristicAnswerScorer(), cascade=off)

    assert ctx.router.completed == []
    assert ctx.only_trace().cascade_stage == CASCADE_OFF


async def test_an_accepted_cheap_answer_is_sent_as_one_frame() -> None:
    ctx = await make_ctx()
    events = await ctx.events(scorer=HeuristicAnswerScorer(), cascade=CASCADE_ON)

    # The strong chain is never opened, and the answer arrives whole.
    assert ctx.router.completed == ["cheap-1"]
    assert ctx.router.streamed == []
    model, token, end = events
    assert isinstance(model, ModelEvent) and model.model_id == "cheap-1"
    assert isinstance(token, TokenEvent) and token.text == GOOD_CHEAP
    assert isinstance(end, MessageEndEvent) and end.content == GOOD_CHEAP
    assert ctx.messages.rows[ctx.messages.order[1]].model_id == "cheap-1"

    trace = ctx.only_trace()
    assert trace.cascade_stage == CASCADE_CHEAP
    assert trace.cheap_model_id == "cheap-1"
    assert trace.cheap_score == 1.0
    assert trace.resolved_model_id == "cheap-1"
    assert [a.model_id for a in trace.attempts] == ["cheap-1"]


async def test_a_rejected_cheap_answer_escalates_and_the_reader_sees_only_the_strong_one() -> None:
    ctx = await make_ctx(SpyRouter(cheap_text="Извините, я не могу ответить на этот вопрос."))
    events = await ctx.events(scorer=HeuristicAnswerScorer(), cascade=CASCADE_ON)

    assert ctx.router.completed == ["cheap-1"]
    assert ctx.router.streamed == ["auto"]
    tokens = [e.text for e in events if isinstance(e, TokenEvent)]
    assert tokens == ["сильный ответ"]

    trace = ctx.only_trace()
    assert trace.cascade_stage == CASCADE_ESCALATED
    assert trace.cheap_model_id == "cheap-1"
    assert trace.cheap_score is not None and trace.cheap_score < 1.0
    assert trace.resolved_model_id == "model-a"
    # Both calls are in one journal, in the order they happened.
    assert [a.model_id for a in trace.attempts] == ["cheap-1", "model-a"]


async def test_an_explicit_pin_disables_the_cascade() -> None:
    ctx = await make_ctx()
    await ctx.events(
        scorer=HeuristicAnswerScorer(), cascade=CASCADE_ON, preferred_model="model-b"
    )

    assert ctx.router.completed == []
    assert ctx.router.streamed == ["model-b"]
    assert ctx.only_trace().cascade_stage == CASCADE_OFF


async def test_a_broken_cheap_stage_leaves_the_normal_path_alone() -> None:
    ctx = await make_ctx(SpyRouter(cheap_error=LLMExhaustedError("нет моделей")))
    events = await ctx.events(scorer=HeuristicAnswerScorer(), cascade=CASCADE_ON)

    assert ctx.router.streamed == ["auto"]
    assert [e.text for e in events if isinstance(e, TokenEvent)] == ["сильный ответ"]
    trace = ctx.only_trace()
    assert trace.cascade_stage == CASCADE_OFF
    assert trace.cheap_model_id is None


async def test_a_missing_scorer_switches_the_cascade_off() -> None:
    ctx = await make_ctx()
    await ctx.events(scorer=None, cascade=CASCADE_ON)

    assert ctx.router.completed == []
    assert ctx.only_trace().cascade_stage == CASCADE_OFF


async def test_a_cheap_answer_the_stub_accepts_needs_no_heuristic() -> None:
    # Proves the use case reads the port, not the concrete scorer.
    ctx = await make_ctx(SpyRouter(cheap_text="что угодно"))
    events = await ctx.events(scorer=StubScorer(ScoreVerdict(0.9, True)), cascade=CASCADE_ON)

    assert [e.text for e in events if isinstance(e, TokenEvent)] == ["что угодно"]
    assert ctx.only_trace().cheap_score == 0.9
