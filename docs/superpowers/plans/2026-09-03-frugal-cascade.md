# FrugalGPT Cascade Implementation Plan (P3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ⚠️ **Read first:** [Prep decisions](./2026-09-03-observability-prep-decisions.md) — the binding contract from phases A–C. Where this plan and that file disagree, **the prep decisions win**.

**Goal:** Дешёвая модель отвечает первой; скорер решает, годится ли ответ; если нет — до первого показанного токена запрос уходит на сильную модель, и это видно в UI.

**Architecture:** Новый use case `application/cascade.py` вызывает `router.complete_chat` на дешёвой модели, прогоняет ответ через порт `AnswerScorer` (эвристическая реализация в адаптерах), и возвращает решение. `chat.py` вызывает его перед обычным стримом: принятый ответ уходит одним `TokenEvent`, отвергнутый — просто не мешает обычному пути. `RunTrace` получает три поля, `GET /lab/pareto` — сводку эскалаций, футер ответа — бейдж.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic, pytest + FakeLLM, React/TS.

**Spec:** `docs/superpowers/specs/2026-09-03-frugal-cascade-design.md`

## Global Constraints

- Домен не импортирует FastAPI/SQLAlchemy/httpx; application — только `app.domain` и `app.application` (проверяется `tests/unit/test_layering.py`)
- Правило «переключение модели только до первого токена» не меняется — каскад решает **до** любого показанного символа
- `CASCADE_ENABLED=false` по умолчанию: выключенный каскад обязан давать ровно сегодняшнее поведение, байт в байт
- Явный пин модели в композере отключает каскад
- Никаких значений секретов; `.env` не читать и не коммитить; FakeLLM в CI
- RU-копирайт только из `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md` — новые строки заводятся там **до** кода
- Deploy только по явной просьбе человека

## File map

| Path | Ответственность |
|------|------------------|
| `apps/api/src/app/domain/cascade.py` | `ScoreVerdict`, константы стадий, порт `AnswerScorer` |
| `apps/api/src/app/domain/tracing.py` | три новых поля `RunTrace` |
| `apps/api/src/app/adapters/llm/heuristic_scorer.py` | эвристический скорер |
| `apps/api/src/app/application/cascade.py` | use case «попробовать дёшево» |
| `apps/api/src/app/application/chat.py` | вызов каскада перед стримом |
| `apps/api/src/app/adapters/persistence/models.py` | колонки в `RunTraceRow` |
| `apps/api/alembic/versions/005_cascade_fields.py` | миграция |
| `apps/api/src/app/adapters/persistence/trace_repo.py` | сохранение + сводка эскалаций |
| `apps/api/src/app/adapters/api/lab.py` | блок `cascade` в ответе pareto |
| `apps/api/src/app/adapters/api/sessions.py` | поля в `/traces` |
| `apps/api/src/app/core/{settings,deps}.py` | конфиг и сборка |
| `apps/web/src/components/{Turn,ParetoPanel}.tsx`, `types.ts`, `api/client.ts` | бейдж и строка эскалаций |

---

### Task 1: Домен каскада

**Files:**
- Create: `apps/api/src/app/domain/cascade.py`
- Modify: `apps/api/src/app/domain/tracing.py`
- Modify: `apps/api/src/app/domain/ports.py`
- Test: `apps/api/tests/unit/test_cascade_entities.py`

**Interfaces:**
- Produces: `ScoreVerdict`, `CASCADE_OFF`, `CASCADE_CHEAP`, `CASCADE_ESCALATED`, `AnswerScorer`; поля `RunTrace.cascade_stage`, `.cheap_model_id`, `.cheap_score`

- [x] **Step 1: Написать падающий тест**

```python
from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF, ScoreVerdict


def test_verdict_carries_reason_when_rejected() -> None:
    verdict = ScoreVerdict(score=0.4, accepted=False, reason="refusal")
    assert verdict.accepted is False
    assert verdict.reason == "refusal"


def test_stages_are_distinct() -> None:
    assert len({CASCADE_OFF, CASCADE_CHEAP, CASCADE_ESCALATED}) == 3
```

- [x] **Step 2: Прогнать — должен упасть на ImportError**

Run: `cd apps/api && uv run pytest tests/unit/test_cascade_entities.py -v`

- [x] **Step 3: Реализовать**

```python
"""Cascade domain: was a cheap answer good enough, and who ended up answering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Каскад выключен или не применялся к этому ответу.
CASCADE_OFF = "off"
#: Ответила дешёвая модель, скорер её принял.
CASCADE_CHEAP = "cheap"
#: Дешёвый ответ отвергнут, отвечала модель из основной цепочки.
CASCADE_ESCALATED = "escalated"

CASCADE_STAGES = frozenset({CASCADE_OFF, CASCADE_CHEAP, CASCADE_ESCALATED})


@dataclass(frozen=True, slots=True)
class ScoreVerdict:
    """Что скорер думает об одном ответе.

    ``reason`` заполняется только при отказе и попадает в трейс: без него
    «эскалировали» — это факт без объяснения, и настраивать порог вслепую.
    """

    score: float
    accepted: bool
    reason: str = ""


class AnswerScorer(Protocol):
    """Решает, годится ли ответ дешёвой модели.

    v1 — эвристика без сетевых вызовов. Порт существует, чтобы LLM-скорер
    можно было подставить, не трогая use case.
    """

    def score(self, question: str, answer: str) -> ScoreVerdict: ...
```

В `tracing.py` добавить в `RunTrace` (после `tool_ok`, до `status`):

```python
    #: off | cheap | escalated — см. app.domain.cascade
    cascade_stage: str = CASCADE_OFF
    #: Кто отвечал первым. None, когда каскад не участвовал.
    cheap_model_id: str | None = None
    #: Вердикт скорера 0..1. None, когда скорер не вызывался.
    cheap_score: float | None = None
```

Импорт в `tracing.py`: `from app.domain.cascade import CASCADE_OFF`.
В `ports.py` ничего добавлять не нужно — порт живёт в `cascade.py` рядом со своим типом.

- [x] **Step 4: Тесты зелёные**

Run: `cd apps/api && uv run pytest tests/unit/test_cascade_entities.py tests/unit/test_layering.py -v`

- [x] **Step 5: Commit**

```bash
git add apps/api/src/app/domain/cascade.py apps/api/src/app/domain/tracing.py apps/api/tests/unit/test_cascade_entities.py
git commit -m "feat(domain): cascade stages and answer scorer port"
```

---

### Task 2: Эвристический скорер

**Files:**
- Create: `apps/api/src/app/adapters/llm/heuristic_scorer.py`
- Test: `apps/api/tests/unit/test_heuristic_scorer.py`

**Interfaces:**
- Consumes: `ScoreVerdict` из Task 1
- Produces: `HeuristicAnswerScorer(min_answer_chars: int = 40, threshold: float = 0.75)`

- [x] **Step 1: Написать падающие тесты — по одному на признак**

```python
import pytest

from app.adapters.llm.heuristic_scorer import HeuristicAnswerScorer

Q = "Объясни, чем очередь отличается от стека."


@pytest.fixture
def scorer() -> HeuristicAnswerScorer:
    return HeuristicAnswerScorer(min_answer_chars=40, threshold=0.75)


def test_accepts_a_complete_answer(scorer: HeuristicAnswerScorer) -> None:
    answer = "Очередь работает по принципу FIFO, а стек — по принципу LIFO. " \
             "Это определяет, какой элемент извлекается первым."
    assert scorer.score(Q, answer).accepted is True


def test_rejects_an_empty_answer(scorer: HeuristicAnswerScorer) -> None:
    verdict = scorer.score(Q, "   ")
    assert verdict.accepted is False
    assert verdict.reason == "too_short"


def test_rejects_a_refusal(scorer: HeuristicAnswerScorer) -> None:
    answer = "Извините, как языковая модель я не могу ответить на этот вопрос сейчас."
    assert scorer.score(Q, answer).reason == "refusal"


def test_rejects_a_truncated_answer(scorer: HeuristicAnswerScorer) -> None:
    answer = "Очередь работает по принципу FIFO, а стек по принципу LIFO, и поэтому"
    assert scorer.score(Q, answer).reason == "truncated"


def test_rejects_an_unclosed_code_fence(scorer: HeuristicAnswerScorer) -> None:
    answer = "Вот пример на Python, он показывает разницу между структурами:\n```python\nq = []"
    assert scorer.score(Q, answer).reason == "unclosed_code"


def test_rejects_a_language_switch(scorer: HeuristicAnswerScorer) -> None:
    answer = "A queue is a FIFO structure while a stack is LIFO, which decides what comes out first."
    assert scorer.score(Q, answer).reason == "language_mismatch"


def test_a_bulleted_answer_is_not_truncated(scorer: HeuristicAnswerScorer) -> None:
    answer = "Ключевые различия между этими структурами данных:\n- очередь: FIFO\n- стек: LIFO"
    assert scorer.score(Q, answer).accepted is True
```

- [x] **Step 2: Прогнать — падает**

Run: `cd apps/api && uv run pytest tests/unit/test_heuristic_scorer.py -v`

- [x] **Step 3: Реализовать**

```python
"""A scorer that costs nothing: no model call, only what the text itself shows.

FrugalGPT trains a scorer. Training one here would spend exactly the budget the
cascade exists to save, so v1 asks the cheapest possible question instead: does
this answer *look* finished, on-topic and in the right language?
"""

from __future__ import annotations

import re

from app.domain.cascade import ScoreVerdict

#: Фразы отказа. Дешёвые модели отказываются заметно чаще дорогих, и это
#: самый однозначный повод эскалировать.
REFUSAL_MARKERS = (
    "как языковая модель",
    "я не могу",
    "не могу помочь",
    "не могу ответить",
    "as an ai language model",
    "i cannot",
    "i can't help",
    "i'm unable to",
)

#: Символы, на которых законченная фраза имеет право закончиться.
TERMINAL_CHARS = ".!?…:»)`\"'"

CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
LATIN = re.compile(r"[a-zA-Z]")


def _script_share(text: str) -> tuple[float, float]:
    cyr = len(CYRILLIC.findall(text))
    lat = len(LATIN.findall(text))
    total = cyr + lat
    if total == 0:
        return 0.0, 0.0
    return cyr / total, lat / total


class HeuristicAnswerScorer:
    """Каждая проверка — один голос. ``score`` — доля пройденных."""

    def __init__(self, min_answer_chars: int = 40, threshold: float = 0.75) -> None:
        self._min_chars = min_answer_chars
        self._threshold = threshold

    def score(self, question: str, answer: str) -> ScoreVerdict:
        text = answer.strip()

        # Порядок важен: слишком короткий ответ нечего проверять дальше, и
        # «обрыв» на нём был бы ложным объяснением.
        if len(text) < self._min_chars:
            return ScoreVerdict(score=0.0, accepted=False, reason="too_short")

        failures: list[str] = []
        lowered = text.lower()

        if any(marker in lowered for marker in REFUSAL_MARKERS):
            failures.append("refusal")

        if text.count("```") % 2 == 1:
            failures.append("unclosed_code")

        if self._looks_truncated(text):
            failures.append("truncated")

        if self._language_switched(question, text):
            failures.append("language_mismatch")

        checks = 4
        score = (checks - len(failures)) / checks
        return ScoreVerdict(
            score=score,
            accepted=not failures and score >= self._threshold,
            reason=failures[0] if failures else "",
        )

    @staticmethod
    def _looks_truncated(text: str) -> bool:
        last_line = text.rstrip().splitlines()[-1].rstrip()
        # Списки и код заканчиваются без точки на законных основаниях.
        if last_line.startswith(("-", "*", "#", ">", "|", "```")) or last_line[:1].isdigit():
            return False
        return last_line[-1:] not in TERMINAL_CHARS

    @staticmethod
    def _language_switched(question: str, answer: str) -> bool:
        q_cyr, _ = _script_share(question)
        a_cyr, a_lat = _script_share(answer)
        if q_cyr < 0.5:  # вопрос не по-русски — сравнивать нечего
            return False
        # Код и термины латиницей — норма, поэтому порог грубый.
        return a_lat > 0.7 and a_cyr < 0.2
```

- [x] **Step 4: Тесты зелёные**

Run: `cd apps/api && uv run pytest tests/unit/test_heuristic_scorer.py -v`

- [x] **Step 5: Commit**

```bash
git add apps/api/src/app/adapters/llm/heuristic_scorer.py apps/api/tests/unit/test_heuristic_scorer.py
git commit -m "feat(llm): heuristic answer scorer for the cascade"
```

---

### Task 3: Use case каскада

**Files:**
- Create: `apps/api/src/app/application/cascade.py`
- Test: `apps/api/tests/unit/test_cascade_use_case.py`

**Interfaces:**
- Consumes: `ChatRouter`, `AnswerScorer`, `AttemptRecord`
- Produces:

```python
@dataclass(slots=True)
class CascadeOutcome:
    accepted_text: str | None      # текст, который можно отдать читателю
    model_id: str | None           # кто его дал
    stage: str                     # CASCADE_OFF | CASCADE_CHEAP | CASCADE_ESCALATED
    cheap_model_id: str | None
    cheap_score: float | None

async def try_cheap_first(...) -> CascadeOutcome: ...
```

- [x] **Step 1: Написать падающие тесты**

```python
from app.application.cascade import try_cheap_first
from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF, ScoreVerdict
from app.domain.entities import ChatMessage, CompletionResult, MessageRole
from app.domain.tracing import AttemptRecord

TURNS = [ChatMessage(role=MessageRole.USER, content="Вопрос про структуры данных?")]


class StubRouter:
    def __init__(self, result: CompletionResult | None = None, error: Exception | None = None):
        self.result, self.error, self.calls = result, error, 0

    async def complete_chat(self, messages, preferred_model="auto", *, generation=None,
                            tools=None, attempts=None):
        self.calls += 1
        if self.error is not None:
            raise self.error
        if attempts is not None:
            assert self.result is not None
            attempts.append(AttemptRecord(model_id=self.result.model_id, ok=True))
        assert self.result is not None
        return self.result


class StubScorer:
    def __init__(self, verdict: ScoreVerdict) -> None:
        self.verdict = verdict

    def score(self, question: str, answer: str) -> ScoreVerdict:
        return self.verdict


async def test_accepted_cheap_answer_is_returned() -> None:
    router = StubRouter(CompletionResult(content="Готовый ответ.", model_id="cheap-1"))
    outcome = await try_cheap_first(
        turns=TURNS, router=router, scorer=StubScorer(ScoreVerdict(1.0, True)),
        cheap_models=["cheap-1"], attempts=[], timeout_seconds=5.0, max_question_chars=1200,
    )
    assert outcome.stage == CASCADE_CHEAP
    assert outcome.accepted_text == "Готовый ответ."
    assert outcome.model_id == "cheap-1"


async def test_rejected_cheap_answer_escalates_without_text() -> None:
    router = StubRouter(CompletionResult(content="Не могу.", model_id="cheap-1"))
    outcome = await try_cheap_first(
        turns=TURNS, router=router, scorer=StubScorer(ScoreVerdict(0.25, False, "refusal")),
        cheap_models=["cheap-1"], attempts=[], timeout_seconds=5.0, max_question_chars=1200,
    )
    assert outcome.stage == CASCADE_ESCALATED
    assert outcome.accepted_text is None
    assert outcome.cheap_score == 0.25


async def test_a_long_question_never_reaches_the_cheap_model() -> None:
    router = StubRouter(CompletionResult(content="x", model_id="cheap-1"))
    long_turns = [ChatMessage(role=MessageRole.USER, content="д" * 5000)]
    outcome = await try_cheap_first(
        turns=long_turns, router=router, scorer=StubScorer(ScoreVerdict(1.0, True)),
        cheap_models=["cheap-1"], attempts=[], timeout_seconds=5.0, max_question_chars=1200,
    )
    assert outcome.stage == CASCADE_OFF
    assert router.calls == 0


async def test_a_provider_failure_falls_through_to_the_normal_path() -> None:
    from app.domain.errors import LLMExhaustedError

    router = StubRouter(error=LLMExhaustedError("нет моделей"))
    outcome = await try_cheap_first(
        turns=TURNS, router=router, scorer=StubScorer(ScoreVerdict(1.0, True)),
        cheap_models=["cheap-1"], attempts=[], timeout_seconds=5.0, max_question_chars=1200,
    )
    assert outcome.stage == CASCADE_OFF
    assert outcome.accepted_text is None


async def test_a_timeout_falls_through_instead_of_raising() -> None:
    import asyncio

    class SlowRouter(StubRouter):
        async def complete_chat(self, messages, preferred_model="auto", *, generation=None,
                                tools=None, attempts=None):
            await asyncio.sleep(1)
            raise AssertionError("should have been cancelled")

    outcome = await try_cheap_first(
        turns=TURNS, router=SlowRouter(), scorer=StubScorer(ScoreVerdict(1.0, True)),
        cheap_models=["cheap-1"], attempts=[], timeout_seconds=0.01, max_question_chars=1200,
    )
    assert outcome.stage == CASCADE_OFF
```

- [x] **Step 2: Прогнать — падает**

Run: `cd apps/api && uv run pytest tests/unit/test_cascade_use_case.py -v`

- [x] **Step 3: Реализовать**

```python
"""Try a cheap model first, and decide *before* the reader sees anything.

The cascade is deliberately allowed to fail: every unexpected outcome — a
provider error, a timeout, a question too long to be worth the gamble — returns
``CASCADE_OFF`` and lets the normal streaming path run untouched. A cost
optimisation must never be able to cost someone their answer.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from app.domain.cascade import CASCADE_CHEAP, CASCADE_ESCALATED, CASCADE_OFF, AnswerScorer
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import LLMExhaustedError, LLMProviderError
from app.domain.ports import ChatRouter
from app.domain.tracing import AttemptRecord

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CascadeOutcome:
    accepted_text: str | None
    model_id: str | None
    stage: str
    cheap_model_id: str | None = None
    cheap_score: float | None = None


def _last_question(turns: list[ChatMessage]) -> str:
    for turn in reversed(turns):
        if turn.role is MessageRole.USER:
            return turn.content
    return ""


async def try_cheap_first(
    *,
    turns: list[ChatMessage],
    router: ChatRouter,
    scorer: AnswerScorer,
    cheap_models: list[str],
    attempts: list[AttemptRecord],
    timeout_seconds: float,
    max_question_chars: int,
) -> CascadeOutcome:
    question = _last_question(turns)
    if not cheap_models or len(question) > max_question_chars:
        return CascadeOutcome(accepted_text=None, model_id=None, stage=CASCADE_OFF)

    cheap_model = cheap_models[0]
    try:
        async with asyncio.timeout(timeout_seconds):
            result = await router.complete_chat(
                turns, cheap_model, attempts=attempts
            )
    except (TimeoutError, LLMExhaustedError, LLMProviderError) as exc:
        # Дешёвый этап — ставка. Проигранная ставка стоит задержки, но не ответа.
        logger.info("cascade cheap stage skipped model_id=%s reason=%s", cheap_model, exc)
        return CascadeOutcome(accepted_text=None, model_id=None, stage=CASCADE_OFF)

    verdict = scorer.score(question, result.content)
    if verdict.accepted:
        return CascadeOutcome(
            accepted_text=result.content,
            model_id=result.model_id,
            stage=CASCADE_CHEAP,
            cheap_model_id=result.model_id,
            cheap_score=verdict.score,
        )

    logger.info(
        "cascade escalating model_id=%s score=%.2f reason=%s",
        result.model_id,
        verdict.score,
        verdict.reason,
    )
    return CascadeOutcome(
        accepted_text=None,
        model_id=None,
        stage=CASCADE_ESCALATED,
        cheap_model_id=result.model_id,
        cheap_score=verdict.score,
    )
```

- [x] **Step 4: Тесты зелёные + слои целы**

Run: `cd apps/api && uv run pytest tests/unit/test_cascade_use_case.py tests/unit/test_layering.py -v`

- [x] **Step 5: Commit**

```bash
git add apps/api/src/app/application/cascade.py apps/api/tests/unit/test_cascade_use_case.py
git commit -m "feat(application): try a cheap model before streaming"
```

---

### Task 4: Подключить каскад к чату

**Files:**
- Modify: `apps/api/src/app/application/chat.py`
- Modify: `apps/api/src/app/core/settings.py`
- Modify: `apps/api/src/app/core/deps.py`
- Modify: `apps/api/src/app/adapters/api/sessions.py`
- Test: `apps/api/tests/unit/test_chat_cascade.py`

**Interfaces:**
- Consumes: `try_cheap_first`, `CascadeOutcome`, `HeuristicAnswerScorer`
- Produces: новые kwargs `send_user_message_and_stream(..., scorer=None, cascade=None)`, где `cascade` — dataclass настроек

- [x] **Step 1: Написать падающие тесты**

```python
# Опираться на существующий стиль tests/unit/test_chat_stream_model_id.py:
# те же фейковые репозитории из tests/unit/fakes.py.
#
# 1. cascade выключен → ровно сегодняшнее поведение: ни одного complete_chat,
#    события совпадают с baseline-тестом.
# 2. cheap принят → читатель получает один TokenEvent с текстом дешёвой модели,
#    ModelEvent с её model_id, MessageEndEvent; router.stream_chat не вызывался.
# 3. cheap отвергнут → стрим идёт как обычно, а в сохранённом трейсе
#    cascade_stage == "escalated" и cheap_model_id заполнен.
# 4. preferred_model задан явно → каскад пропущен (router.complete_chat не звали).
```

- [x] **Step 2: Прогнать — падает**

Run: `cd apps/api && uv run pytest tests/unit/test_chat_cascade.py -v`

- [x] **Step 3: Реализовать в `chat.py`**

Настройки каскада передаются одним объектом, чтобы не разносить шесть kwargs:

```python
@dataclass(slots=True, frozen=True)
class CascadeSettings:
    enabled: bool
    cheap_models: list[str]
    timeout_seconds: float
    max_question_chars: int
```

Вызов ставится **после** media-раунда и **до** `router.stream_chat`, потому что
tool-раунд не участвует в каскаде (см. спеку), а решение обязано быть принято до
первого токена:

```python
    cascade_stage = CASCADE_OFF
    cheap_model_id: str | None = None
    cheap_score: float | None = None

    # Явный пин человека сильнее автоматики — то же правило, что и для penalty.
    pinned = model not in ("", AUTO_MODEL)
    if cascade is not None and cascade.enabled and scorer is not None and not pinned:
        outcome = await try_cheap_first(
            turns=turns, router=router, scorer=scorer,
            cheap_models=cascade.cheap_models, attempts=attempts,
            timeout_seconds=cascade.timeout_seconds,
            max_question_chars=cascade.max_question_chars,
        )
        cascade_stage = outcome.stage
        cheap_model_id = outcome.cheap_model_id
        cheap_score = outcome.cheap_score
        if outcome.accepted_text is not None and outcome.model_id is not None:
            resolved_model = outcome.model_id
            draft.model_id = resolved_model
            yield ModelEvent(model_id=resolved_model)
            accumulated.append(outcome.accepted_text)
            # Один фрейм, а не имитация печати: ответ уже готов целиком.
            yield TokenEvent(text=outcome.accepted_text)
            if first_token_at is None:
                first_token_at = time.monotonic()
            answer = await finalize(resolved_model)
            yield MessageEndEvent(
                message_id=assistant.id, content=answer, model_id=resolved_model
            )
            return
```

Три поля прокинуть в `RunTrace(...)` внутри `save_trace`.

Settings (имена из спеки, значения — дефолты):

```python
    cascade_enabled: bool = False
    cascade_cheap_models: str = ""
    cascade_score_threshold: float = 0.75
    cascade_min_answer_chars: int = 40
    cascade_max_cheap_chars: int = 1200
    cascade_timeout_seconds: float = 12.0

    def cascade_cheap_models_list(self) -> list[str]:
        explicit = _csv(self.cascade_cheap_models)
        if explicit:
            return explicit
        chain = self.model_chain_list()
        return chain[:1]
```

`deps.py`: собрать `HeuristicAnswerScorer(min_answer_chars=…, threshold=…)` в `Container.scorer`.
`sessions.py`: передать `scorer=container.scorer` и `cascade=CascadeSettings(...)` в use case.

- [x] **Step 4: Тесты зелёные, включая существующие**

Run: `cd apps/api && uv run pytest -q` — ни один существующий тест не должен измениться: выключенный каскад обязан быть неотличим от сегодняшнего поведения.

- [x] **Step 5: Commit**

```bash
git add apps/api/src/app/application/chat.py apps/api/src/app/core/settings.py apps/api/src/app/core/deps.py apps/api/src/app/adapters/api/sessions.py apps/api/tests/unit/test_chat_cascade.py
git commit -m "feat(chat): escalate from a cheap model before the first token"
```

---

### Task 5: Персистентность

**Files:**
- Modify: `apps/api/src/app/adapters/persistence/models.py`
- Create: `apps/api/alembic/versions/005_cascade_fields.py`
- Modify: `apps/api/src/app/adapters/persistence/trace_repo.py`
- Test: `apps/api/tests/unit/test_trace_repo_cascade.py`

- [x] **Step 1: Колонки в `RunTraceRow`**

```python
    cascade_stage: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CASCADE_OFF, server_default=CASCADE_OFF
    )
    cheap_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cheap_score: Mapped[float | None] = mapped_column(Float, nullable=True)
```

- [x] **Step 2: Миграция**

```python
"""cascade fields on run traces

Revision ID: 005
Revises: 004
Create Date: 2026-09-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "run_traces",
        sa.Column("cascade_stage", sa.String(length=16), nullable=False, server_default="off"),
    )
    op.add_column("run_traces", sa.Column("cheap_model_id", sa.String(length=128), nullable=True))
    op.add_column("run_traces", sa.Column("cheap_score", sa.Float(), nullable=True))
    # Сводка эскалаций читает окно по времени и фильтрует по стадии.
    op.create_index("ix_run_traces_cascade_stage", "run_traces", ["cascade_stage", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_run_traces_cascade_stage", table_name="run_traces")
    op.drop_column("run_traces", "cheap_score")
    op.drop_column("run_traces", "cheap_model_id")
    op.drop_column("run_traces", "cascade_stage")
```

- [x] **Step 3: Репозиторий — маппинг трёх полей в обе стороны плюс сводка**

```python
    async def cascade_summary(self, *, since: datetime, until: datetime) -> CascadeSummary | None:
        """None, когда в окне нет ни одного прогона с включённым каскадом."""
```

`CascadeSummary` — `@dataclass(frozen=True)` в `domain/cascade.py`: `total`, `cheap`, `escalated`
и `escalation_rate` как `property`.

- [x] **Step 4: Тесты зелёные** (`uv run pytest -q`, плюс `RUN_INTEGRATION=1` на одноразовой БД)

- [x] **Step 5: Commit**

```bash
git add apps/api/src/app/adapters/persistence apps/api/alembic/versions/005_cascade_fields.py apps/api/src/app/domain/cascade.py apps/api/tests/unit/test_trace_repo_cascade.py
git commit -m "feat(db): persist cascade stage on run traces"
```

---

### Task 6: API

**Files:**
- Modify: `apps/api/src/app/adapters/api/lab.py`
- Modify: `apps/api/src/app/adapters/api/sessions.py`
- Test: `apps/api/tests/unit/test_lab_cascade_api.py`

- [ ] **Step 1: Тест на форму ответа**

```python
def test_pareto_reports_the_escalation_summary(...) -> None:
    body = client.get("/api/v1/lab/pareto?hours=24").json()
    assert body["cascade"] == {
        "total": 3, "cheap": 2, "escalated": 1, "escalation_rate": pytest.approx(1 / 3)
    }


def test_pareto_omits_the_summary_when_the_cascade_never_ran(...) -> None:
    assert client.get("/api/v1/lab/pareto?hours=24").json()["cascade"] is None
```

- [ ] **Step 2: Реализовать** — `cascade: CascadeSummaryResponse | None = None` в модели ответа
  pareto; три поля в элементе `/sessions/{id}/traces`.

- [ ] **Step 3: Тесты зелёные**

- [ ] **Step 4: Commit** `feat(api): expose cascade stage and escalation rate`

---

### Task 7: UI

**Files:**
- Modify: `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md` (сначала!)
- Modify: `apps/web/src/api/client.ts`, `apps/web/src/types.ts`
- Modify: `apps/web/src/components/Chat.tsx`, `Turn.tsx`, `ParetoPanel.tsx`
- Modify: `apps/web/src/index.css`

- [ ] **Step 1: Завести строки в чеклисте**

| Key | String |
|-----|--------|
| `escalated_badge` | эскалировали |
| `escalated_hint` | Дешёвая модель не справилась — ответила модель посильнее |
| `escalation_rate` | Эскалации: {n} из {total} ({percent}%) |

- [ ] **Step 2: Бейдж в футере** — `Turn.tsx`, рядом с бейджем модели, только при
  `turn.cascadeStage === "escalated"`. Стиль: существующий `.badge`, без нового цвета.
  Источник значения — `message_end`? Нет: стадия известна только серверу, поэтому поле
  добавляется к `MessageDto` тем же способом, что и `feedback` (см. фазу B),
  и в `toTurn`. У живого ответа бейдж появляется после `message_end`, как и оценка.

- [ ] **Step 3: Строка эскалаций** под таблицей в `ParetoPanel.tsx`, только когда
  `data.cascade !== null`. Одна строка `.pareto-meta`, без новой секции.

- [ ] **Step 4: Проверить** `npx tsc -b --noEmit` и `npm run lint` (базовая линия — 7 warnings,
  ни одного из новых файлов)

- [ ] **Step 5: Commit** `feat(web): show when an answer was escalated`

---

### Task 8: Верификация и документация

- [ ] **Step 1:** `cd apps/api && uv run pytest -q && uv run ruff check src tests && uv run mypy src`
- [ ] **Step 2:** Интеграционный прогон на одноразовом Postgres с `RUN_INTEGRATION=1`
- [ ] **Step 3:** Живой стенд: включить `CASCADE_ENABLED=true`, отправить короткий и длинный
      вопросы, убедиться, что бейдж «эскалировали» появляется только на втором,
      а строка эскалаций в Рейтинге считает их
- [ ] **Step 4:** Дописать имена переменных в `.env.example` и `docs/env-local.md`
      (**только имена**, значений в репозитории нет)
- [ ] **Step 5:** Отметить D.2 в мастер-плане; обновить индекс `deferred-features.md`
- [ ] **Step 6: Commit** `docs: cascade env knobs and phase D status`

---

## Self-review

- **Покрытие спеки:** cheap-этап не-стримом — Task 3–4; скорер — Task 2 (порт в Task 1);
  три поля трейса — Task 1 + 5; конфиг — Task 4; API — Task 6; бейдж и строка — Task 7;
  тестовая матрица из спеки — Tasks 2–4 и 8.
- **Плейсхолдеров нет:** каждый шаг с кодом несёт код. Исключение осознанное — Task 4 Step 1
  и Task 5 Step 3 описывают тесты и маппинг словами, потому что опираются на существующие
  фикстуры репозитория; исполнитель читает соседний файл, а не догадывается.
- **Согласованность типов:** `ScoreVerdict` (Task 1) → `HeuristicAnswerScorer.score` (Task 2)
  → `try_cheap_first` (Task 3) → `CascadeSettings` (Task 4) → колонки (Task 5) → ответы (Task 6)
  → `cascadeStage` (Task 7). `CASCADE_OFF|CHEAP|ESCALATED` — одни и те же строки на всём пути.
- **Риск, принятый сознательно:** отвергнутый дешёвый ответ стоит читателю лишнего ожидания.
  Ограничен таймаутом и длиной вопроса; наблюдается через `escalation_rate`.
