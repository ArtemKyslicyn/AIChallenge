"""The cheap stage decides before the reader sees anything — or gets out of the way."""

import asyncio
from typing import Any

from app.application.cascade import try_cheap_first
from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF, ScoreVerdict
from app.domain.entities import ChatMessage, CompletionResult, MessageRole
from app.domain.errors import LLMExhaustedError, LLMProviderError
from app.domain.tracing import AttemptRecord

TURNS = [ChatMessage(role=MessageRole.USER, content="Вопрос про структуры данных?")]


class StubRouter:
    def __init__(
        self, result: CompletionResult | None = None, error: Exception | None = None
    ) -> None:
        self.result, self.error, self.calls = result, error, 0

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = "auto",
        *,
        generation: Any = None,
        tools: Any = None,
        attempts: list[AttemptRecord] | None = None,
    ) -> CompletionResult:
        self.calls += 1
        self.last_model = preferred_model
        if self.error is not None:
            raise self.error
        assert self.result is not None
        if attempts is not None:
            attempts.append(AttemptRecord(model_id=self.result.model_id, ok=True))
        return self.result

    def stream_chat(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("the cascade must not stream")


class StubScorer:
    def __init__(self, verdict: ScoreVerdict) -> None:
        self.verdict = verdict
        self.seen: tuple[str, str] | None = None

    def score(self, question: str, answer: str) -> ScoreVerdict:
        self.seen = (question, answer)
        return self.verdict


async def run(
    router: Any,
    verdict: ScoreVerdict,
    *,
    turns: list[ChatMessage] | None = None,
    cheap_models: list[str] | None = None,
    attempts: list[AttemptRecord] | None = None,
    timeout_seconds: float = 5.0,
    scorer: Any = None,
) -> Any:
    return await try_cheap_first(
        turns=turns if turns is not None else TURNS,
        router=router,
        scorer=scorer if scorer is not None else StubScorer(verdict),
        cheap_models=cheap_models if cheap_models is not None else ["cheap-1"],
        attempts=attempts if attempts is not None else [],
        timeout_seconds=timeout_seconds,
        max_question_chars=1200,
    )


async def test_accepted_cheap_answer_is_returned() -> None:
    router = StubRouter(CompletionResult(content="Готовый ответ.", model_id="cheap-1"))
    outcome = await run(router, ScoreVerdict(1.0, True))

    assert outcome.stage == CASCADE_CHEAP
    assert outcome.accepted_text == "Готовый ответ."
    assert outcome.model_id == "cheap-1"
    assert outcome.cheap_model_id == "cheap-1"
    assert outcome.cheap_score == 1.0


async def test_the_cheap_attempt_lands_in_the_request_journal() -> None:
    router = StubRouter(CompletionResult(content="Готовый ответ.", model_id="cheap-1"))
    attempts: list[AttemptRecord] = []
    await run(router, ScoreVerdict(1.0, True), attempts=attempts)

    # The ranking counts it like any other call — no separate bookkeeping.
    assert [(a.model_id, a.ok) for a in attempts] == [("cheap-1", True)]


async def test_rejected_cheap_answer_escalates_without_text() -> None:
    router = StubRouter(CompletionResult(content="Не могу.", model_id="cheap-1"))
    outcome = await run(router, ScoreVerdict(0.25, False, "refusal"))

    assert outcome.stage == CASCADE_ESCALATED
    assert outcome.accepted_text is None
    assert outcome.model_id is None
    assert outcome.cheap_model_id == "cheap-1"
    assert outcome.cheap_score == 0.25


async def test_the_scorer_sees_the_last_user_turn_not_the_system_prompt() -> None:
    router = StubRouter(CompletionResult(content="Ответ.", model_id="cheap-1"))
    scorer = StubScorer(ScoreVerdict(1.0, True))
    turns = [
        ChatMessage(role=MessageRole.SYSTEM, content="Ты ассистент."),
        ChatMessage(role=MessageRole.USER, content="Первый вопрос?"),
        ChatMessage(role=MessageRole.ASSISTANT, content="Первый ответ."),
        ChatMessage(role=MessageRole.USER, content="Свежий вопрос?"),
    ]
    await run(router, ScoreVerdict(1.0, True), turns=turns, scorer=scorer)

    assert scorer.seen == ("Свежий вопрос?", "Ответ.")


async def test_a_long_question_never_reaches_the_cheap_model() -> None:
    router = StubRouter(CompletionResult(content="x", model_id="cheap-1"))
    long_turns = [ChatMessage(role=MessageRole.USER, content="д" * 5000)]
    outcome = await run(router, ScoreVerdict(1.0, True), turns=long_turns)

    assert outcome.stage == CASCADE_OFF
    assert router.calls == 0


async def test_an_empty_cheap_chain_is_a_no_op() -> None:
    router = StubRouter(CompletionResult(content="x", model_id="cheap-1"))
    outcome = await run(router, ScoreVerdict(1.0, True), cheap_models=[])

    assert outcome.stage == CASCADE_OFF
    assert router.calls == 0


async def test_a_provider_failure_falls_through_to_the_normal_path() -> None:
    router = StubRouter(error=LLMExhaustedError("нет моделей"))
    outcome = await run(router, ScoreVerdict(1.0, True))

    assert outcome.stage == CASCADE_OFF
    assert outcome.accepted_text is None
    assert outcome.cheap_model_id is None


async def test_a_provider_error_also_falls_through() -> None:
    router = StubRouter(error=LLMProviderError("boom", status=500))
    assert (await run(router, ScoreVerdict(1.0, True))).stage == CASCADE_OFF


async def test_a_timeout_falls_through_instead_of_raising() -> None:
    class SlowRouter(StubRouter):
        async def complete_chat(
            self,
            messages: list[ChatMessage],
            preferred_model: str = "auto",
            *,
            generation: Any = None,
            tools: Any = None,
            attempts: list[AttemptRecord] | None = None,
        ) -> CompletionResult:
            await asyncio.sleep(1)
            raise AssertionError("should have been cancelled")

    outcome = await run(SlowRouter(), ScoreVerdict(1.0, True), timeout_seconds=0.01)
    assert outcome.stage == CASCADE_OFF
