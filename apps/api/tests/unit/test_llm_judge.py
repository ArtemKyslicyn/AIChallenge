"""The judge adapter: it may return nothing, but it may never raise.

Every test here is really one assertion — a judge has no right to break, slow
or bias the chat it is measuring.
"""

import asyncio
from pathlib import Path
from typing import Any

import pytest

from app.adapters.lab.rubric import JudgeRubric, load_judge_rubric
from app.adapters.llm.llm_judge import HourlyJudgeBudget, LLMAnswerJudge
from app.domain.entities import ChatMessage, CompletionResult, MessageRole
from app.domain.errors import LLMExhaustedError, LLMProviderError
from app.domain.tracing import AttemptRecord

CLEAN = '{"relevance": 5, "completeness": 4, "clarity": 3}'
RUBRIC = JudgeRubric(
    system="Ты оцениваешь ответ.",
    template='Вопрос:\n{question}\n\nОтвет:\n{answer}\n\nФормат: {"relevance": N}',
)


class StubRouter:
    def __init__(
        self,
        content: str = CLEAN,
        *,
        error: Exception | None = None,
        model_id: str = "judge-1",
        delay: float = 0.0,
    ) -> None:
        self.content, self.error, self.model_id, self.delay = content, error, model_id, delay
        self.calls = 0
        self.seen: list[ChatMessage] = []
        self.last_model = ""

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
        self.seen = list(messages)
        self.last_model = preferred_model
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return CompletionResult(content=self.content, model_id=self.model_id)

    def stream_chat(self, *args: Any, **kwargs: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("the judge must not stream")


def judge_for(router: Any, *, model_id: str = "judge-1", timeout: float = 5.0) -> LLMAnswerJudge:
    return LLMAnswerJudge(
        router=router, model_id=model_id, rubric=RUBRIC, timeout_seconds=timeout
    )


async def test_judge_returns_a_verdict_for_a_clean_answer() -> None:
    router = StubRouter()
    verdict = await judge_for(router).judge("в?", "о." * 60, answered_by="model-a")
    assert verdict is not None
    assert verdict.score == pytest.approx(12 / 15)
    # Оценка приписывается той модели, которая её реально поставила.
    assert verdict.judge_model_id == "judge-1"
    assert router.last_model == "judge-1"


async def test_the_prompt_carries_the_rubric_the_question_and_the_answer() -> None:
    router = StubRouter()
    await judge_for(router).judge("сколько будет 2+2?", "четыре", answered_by="model-a")
    system, user = router.seen
    assert system.role is MessageRole.SYSTEM and system.content == RUBRIC.system
    assert "сколько будет 2+2?" in user.content
    assert "четыре" in user.content
    # Пример формата в шаблоне — это фигурные скобки; подстановка не имеет
    # права на них споткнуться.
    assert '{"relevance": N}' in user.content


async def test_judge_returns_none_when_the_answer_was_written_by_the_judge() -> None:
    # Модели систематически предпочитают собственный текст. Оценка,
    # поставленная самому себе, хуже отсутствия оценки.
    router = StubRouter()
    assert await judge_for(router).judge("в?", "о.", answered_by="judge-1") is None
    assert router.calls == 0


async def test_judge_returns_none_when_the_chain_answered_with_the_judged_model() -> None:
    # Пин судьи не гарантирован: цепочка могла свалиться обратно на автора.
    router = StubRouter(model_id="model-a")
    assert await judge_for(router).judge("в?", "о.", answered_by="model-a") is None


@pytest.mark.parametrize(
    "error",
    [LLMProviderError("boom", status=429), LLMExhaustedError("nothing left"), RuntimeError("odd")],
)
async def test_judge_returns_none_when_the_provider_fails(error: Exception) -> None:
    assert await judge_for(StubRouter(error=error)).judge("в?", "о.", answered_by="m") is None


async def test_judge_returns_none_on_timeout() -> None:
    router = StubRouter(delay=5.0)
    verdict = await judge_for(router, timeout=0.01).judge("в?", "о.", answered_by="m")
    assert verdict is None


async def test_judge_returns_none_when_the_verdict_cannot_be_read() -> None:
    router = StubRouter(content="я подумаю об этом позже")
    assert await judge_for(router).judge("в?", "о.", answered_by="m") is None


async def test_a_judge_without_a_model_id_never_calls_anything() -> None:
    router = StubRouter()
    assert await judge_for(router, model_id="").judge("в?", "о.", answered_by="m") is None
    assert router.calls == 0


def test_rubric_loads_from_the_repo_config() -> None:
    lab_dir = Path(__file__).resolve().parents[4] / "configs" / "lab"
    rubric = load_judge_rubric(lab_dir)
    assert rubric is not None
    assert "{question}" in rubric.template and "{answer}" in rubric.template
    assert rubric.system.strip()


def test_a_missing_rubric_is_none_rather_than_a_crash(tmp_path: Path) -> None:
    # Битая конфигурация выключает судью, но не роняет процесс на старте.
    assert load_judge_rubric(tmp_path) is None
    (tmp_path / "judge_rubric.yaml").write_text("system: only\n", encoding="utf-8")
    assert load_judge_rubric(tmp_path) is None


def test_the_hourly_budget_forgets_last_hour() -> None:
    clock = [1000.0]
    budget = HourlyJudgeBudget(now=lambda: clock[0])
    assert budget.used() == 0
    budget.take()
    budget.take()
    assert budget.used() == 2
    clock[0] += 3601
    assert budget.used() == 0
