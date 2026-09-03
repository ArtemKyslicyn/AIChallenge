# Quality Column (G-Eval) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ⚠️ **Read first:** [Prep decisions](./2026-09-03-observability-prep-decisions.md) — the binding contract from phases A–D. Where this plan and that file disagree, **the prep decisions win**.

**Goal:** Добавить в Рейтинг ось качества, чтобы быстрая дешёвая модель, отвечающая мимо вопроса, перестала выигрывать таблицу.

**Architecture:** Судья вызывается **после** доставки ответа, отдельной задачей через существующий `run_shielded` со своей сессией БД — он физически не в пути SSE. Оценка пишется в `run_traces`, агрегат получает `avg_quality`/`judged_n`, и Score начинает считаться по качеству только когда оценок набралось достаточно.

**Tech Stack:** FastAPI + SQLAlchemy + Alembic, YAML-рубрика в `configs/lab/`, pytest + FakeLLM, React/TS.

**Spec:** `docs/superpowers/specs/2026-09-03-quality-column-design.md`

## Global Constraints

- `JUDGE_MODEL` пуст по умолчанию → фича выключена, и выключенной она обязана давать **ровно** сегодняшнее поведение и ровно сегодняшний Score
- Судья никогда не вызывается синхронно в пути SSE и никогда не может уронить ответ
- Судья не может быть той же моделью, что писала ответ (self-preference); при совпадении оценка не сохраняется
- Домен не импортирует фреймворки; application — только `app.domain`/`app.application` (`tests/unit/test_layering.py`)
- Невалидный ответ судьи → `None`, никогда не `0.0`
- RU-копирайт только из `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md`, новые строки заводятся там до кода
- Секреты не читаем и не коммитим; FakeLLM в CI; deploy только по явной просьбе

## File map

| Path | Ответственность |
|------|------------------|
| `apps/api/src/app/domain/quality.py` | `QualityVerdict`, порт `AnswerJudge` |
| `apps/api/src/app/domain/tracing.py` | `quality_score`, `quality_model_id`; `avg_quality`, `judged_n` в `ModelAggregate` |
| `apps/api/src/app/application/quality.py` | разбор ответа судьи + сэмплер (чистые функции) |
| `apps/api/src/app/application/pareto.py` | Score с ветвлением по `judged_n` |
| `apps/api/src/app/adapters/llm/llm_judge.py` | судья поверх `ChatRouter.complete_chat` |
| `apps/api/src/app/adapters/lab/rubric.py` | загрузка рубрики из YAML |
| `configs/lab/judge_rubric.yaml` | критерии и промпт |
| `apps/api/alembic/versions/006_quality_score.py` | миграция |
| `apps/api/src/app/adapters/api/sessions.py` | запуск судьи вне запроса |
| `apps/web/src/components/ParetoPanel.tsx`, `index.css` | колонка «Качество» |

---

### Task 1: Домен качества

**Files:**
- Create: `apps/api/src/app/domain/quality.py`
- Modify: `apps/api/src/app/domain/tracing.py`
- Test: `apps/api/tests/unit/test_quality_entities.py`

**Interfaces:**
- Produces: `QualityVerdict(score: float, sub_scores: dict[str, int], judge_model_id: str)`, порт `AnswerJudge`; поля `RunTrace.quality_score`, `.quality_model_id`; `ModelAggregate.avg_quality`, `.judged_n`

- [x] **Step 1: Падающий тест**

```python
from app.domain.quality import QualityVerdict


def test_verdict_keeps_the_sub_scores_it_was_built_from() -> None:
    verdict = QualityVerdict(
        score=0.8, sub_scores={"relevance": 4, "completeness": 4, "clarity": 4},
        judge_model_id="judge-1",
    )
    assert verdict.score == 0.8
    assert verdict.sub_scores["relevance"] == 4
```

- [x] **Step 2: Прогнать — падает.** `cd apps/api && uv run pytest tests/unit/test_quality_entities.py -v`

- [x] **Step 3: Реализовать**

```python
"""Quality domain: what a judge thought of one answer.

Sub-scores are kept, not just their average: when a rubric turns out to be
badly calibrated, the only way to see *which* criterion is misfiring is to have
kept them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

#: Критерии рубрики. Порядок фиксирован — по нему собирается промпт и разбор.
RUBRIC_CRITERIA = ("relevance", "completeness", "clarity")
#: Верхняя граница одного критерия. G-Eval-style form filling, шкала 0..5.
CRITERION_MAX = 5


@dataclass(frozen=True, slots=True)
class QualityVerdict:
    score: float
    sub_scores: dict[str, int] = field(default_factory=dict)
    judge_model_id: str = ""


class AnswerJudge(Protocol):
    """Оценивает один ответ. Возвращает None, когда оценить не удалось.

    None — это «не знаем», а не «плохо»: подстановка нуля превратила бы сбой
    разбора в приговор модели.
    """

    async def judge(self, question: str, answer: str, *, answered_by: str) -> QualityVerdict | None: ...
```

В `tracing.py` — в конец `RunTrace` (там же, где живут поля каскада, и по той же причине: дефолты нельзя ставить перед полями без дефолтов):

```python
    #: Оценка судьи 0..1. None — не судили или разбор не удался.
    quality_score: float | None = None
    #: Кто судил. Нужен, чтобы агрегаты не смешивали двух разных судей молча.
    quality_model_id: str | None = None
```

В `ModelAggregate` — два поля; оба нужны, потому что среднее без размера выборки читается как факт:

```python
    avg_quality: float | None = None
    judged_n: int = 0
```

- [x] **Step 4: Тесты зелёные.** `uv run pytest tests/unit/test_quality_entities.py tests/unit/test_layering.py -v`
- [x] **Step 5: Commit** `feat(domain): quality verdict and judge port`

---

### Task 2: Разбор ответа судьи и сэмплер

**Files:**
- Create: `apps/api/src/app/application/quality.py`
- Test: `apps/api/tests/unit/test_quality_parsing.py`

**Interfaces:**
- Produces: `parse_verdict(raw: str, *, judge_model_id: str) -> QualityVerdict | None`, `should_judge(...) -> bool`

- [ ] **Step 1: Падающие тесты**

```python
import pytest

from app.application.quality import parse_verdict, should_judge


def test_parses_a_clean_verdict() -> None:
    verdict = parse_verdict(
        '{"relevance": 5, "completeness": 4, "clarity": 3}', judge_model_id="j"
    )
    assert verdict is not None
    assert verdict.score == pytest.approx(12 / 15)
    assert verdict.judge_model_id == "j"


def test_parses_a_verdict_wrapped_in_a_code_fence() -> None:
    raw = '```json\n{"relevance": 5, "completeness": 5, "clarity": 5}\n```'
    verdict = parse_verdict(raw, judge_model_id="j")
    assert verdict is not None and verdict.score == 1.0


@pytest.mark.parametrize(
    "raw",
    [
        "это не json вовсе",
        "{}",
        '{"relevance": 5, "clarity": 5}',            # нет completeness
        '{"relevance": 9, "completeness": 5, "clarity": 5}',   # вне диапазона
        '{"relevance": "пять", "completeness": 5, "clarity": 5}',
    ],
)
def test_a_broken_verdict_is_none_not_zero(raw: str) -> None:
    # Ноль означал бы «судья счёл ответ плохим». Сбой разбора — это «не знаем».
    assert parse_verdict(raw, judge_model_id="j") is None


def test_sampler_respects_the_status_and_length_gates() -> None:
    assert should_judge(status="error", answer_chars=500, rate=1.0, roll=0.0,
                        judged_this_hour=0, max_per_hour=60) is False
    assert should_judge(status="ok", answer_chars=10, rate=1.0, roll=0.0,
                        judged_this_hour=0, max_per_hour=60, min_answer_chars=80) is False


def test_sampler_respects_the_hourly_cap_and_the_rate() -> None:
    common = dict(status="ok", answer_chars=500, min_answer_chars=80)
    assert should_judge(**common, rate=1.0, roll=0.0, judged_this_hour=60, max_per_hour=60) is False
    assert should_judge(**common, rate=0.2, roll=0.5, judged_this_hour=0, max_per_hour=60) is False
    assert should_judge(**common, rate=0.2, roll=0.1, judged_this_hour=0, max_per_hour=60) is True
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализовать.** `roll` передаётся снаружи (значение `random.random()`), чтобы функция осталась чистой и тестировалась без подмены модуля. Разбор: срезать ограждение кода, `json.loads`, проверить наличие **всех** `RUBRIC_CRITERIA`, что каждое — `int` в `0..CRITERION_MAX`, сложить и поделить на `len(RUBRIC_CRITERIA) * CRITERION_MAX`. Любое отклонение → `None` плюс `logger.info` с причиной.

- [ ] **Step 4: Тесты зелёные**
- [ ] **Step 5: Commit** `feat(application): parse judge verdicts and sample what to judge`

---

### Task 3: Рубрика и адаптер судьи

**Files:**
- Create: `configs/lab/judge_rubric.yaml`
- Create: `apps/api/src/app/adapters/lab/rubric.py`
- Create: `apps/api/src/app/adapters/llm/llm_judge.py`
- Test: `apps/api/tests/unit/test_llm_judge.py`

**Interfaces:**
- Consumes: `ChatRouter.complete_chat`, `parse_verdict`
- Produces: `LLMAnswerJudge(router, model_id, rubric, timeout_seconds)` реализующий `AnswerJudge`

- [ ] **Step 1: Падающие тесты**

```python
async def test_judge_returns_none_when_the_answer_was_written_by_the_judge() -> None:
    # Модели систематически предпочитают собственный текст. Оценка,
    # поставленная самому себе, хуже отсутствия оценки.
    judge = LLMAnswerJudge(router=StubRouter(...), model_id="judge-1", rubric=RUBRIC, timeout_seconds=5)
    assert await judge.judge("в?", "о.", answered_by="judge-1") is None


async def test_judge_returns_none_when_the_provider_fails() -> None: ...
async def test_judge_returns_none_on_timeout(...) -> None: ...
async def test_judge_returns_a_verdict_for_a_clean_answer(...) -> None: ...
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализовать.** YAML держит `system` и `template` с плейсхолдерами `{question}` и `{answer}`; загрузчик повторяет стиль `adapters/lab/presets.py`. Адаптер оборачивает вызов в `asyncio.timeout` и глотает `LLMProviderError | LLMExhaustedError | TimeoutError` в `None` с `logger.info`. Никаких исключений наружу: у судьи нет права ничего сломать.

```yaml
# configs/lab/judge_rubric.yaml
system: |
  Ты оцениваешь ответ ассистента по трём критериям. Отвечай строго JSON-объектом
  без пояснений и без ограждения кода.
template: |
  Вопрос:
  {question}

  Ответ:
  {answer}

  Оцени каждый критерий целым числом от 0 до 5:
  - relevance — отвечает ли текст на заданный вопрос
  - completeness — покрыта ли суть вопроса
  - clarity — понятно ли written, без противоречий и обрывов

  Формат: {"relevance": N, "completeness": N, "clarity": N}
```

- [ ] **Step 4: Тесты зелёные**
- [ ] **Step 5: Commit** `feat(llm): rubric-driven answer judge`

---

### Task 4: Персистентность и агрегат

**Files:**
- Modify: `apps/api/src/app/adapters/persistence/models.py`, `trace_repo.py`
- Create: `apps/api/alembic/versions/006_quality_score.py` (revision "006", down_revision "005")
- Modify: `apps/api/src/app/application/pareto.py`
- Test: `apps/api/tests/unit/test_pareto_quality.py`

- [ ] **Step 1: Падающий тест на ветвление формулы**

```python
def test_score_ignores_quality_until_there_are_enough_judged_runs() -> None:
    # Включение судьи не имеет права задним числом переставить таблицу.
    aggregates = aggregate_models(rows_with_two_judged_runs, min_judged_runs=5)
    assert aggregates[0].score == pytest.approx(score_from_success_rate)


def test_score_uses_quality_once_the_sample_is_big_enough() -> None:
    aggregates = aggregate_models(rows_with_seven_judged_runs, min_judged_runs=5)
    assert aggregates[0].score == pytest.approx(avg_quality / latency_s / cost)
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализовать.** Две колонки (`quality_score` Float nullable, `quality_model_id` String(128) nullable), индекса не нужно — агрегат и так читает окно. `aggregate_models` получает `min_judged_runs` и считает `avg_quality` только по строкам с непустой оценкой; `judged_n` — их число. Ветвление ровно как в спеке.

- [ ] **Step 4: Тесты зелёные, включая существующий `test_pareto.py` без правок**
- [ ] **Step 5: Commit** `feat(db): persist judge scores and rank by quality`

---

### Task 5: Запуск судьи вне пути SSE

**Files:**
- Modify: `apps/api/src/app/adapters/api/sessions.py`
- Modify: `apps/api/src/app/core/{settings,deps}.py`
- Test: `apps/api/tests/unit/test_judge_scheduling.py`

- [ ] **Step 1: Падающие тесты**

```python
async def test_the_judge_is_never_awaited_inside_the_stream() -> None:
    # Фейковый судья, который спит дольше теста: если бы его ждали в пути
    # запроса, тест бы не завершился.
    ...

async def test_a_failing_judge_leaves_the_answer_and_the_trace_alone() -> None: ...
async def test_no_judge_model_configured_means_no_call_at_all() -> None: ...
```

- [ ] **Step 2: Прогнать — падает**

- [ ] **Step 3: Реализовать.** После завершения стрима, там же где живёт `_rescue_unsaved`, поставить задачу через `run_shielded`: открыть **свою** сессию из `container.sessionmaker()`, свериться с `should_judge`, вызвать судью, записать оценку в трейс сообщения, закоммитить. Любое исключение — `logger.warning` и выход. Счётчик судейств за час — в процессе, рядом с `FeedbackPenaltyCache` по стилю.

Настройки (имена из спеки): `judge_model=""`, `judge_sample_rate=0.2`, `judge_min_answer_chars=80`, `judge_max_per_hour=60`, `judge_min_runs=5`, `judge_timeout_seconds=20.0`. Пустой `judge_model` → судья не собирается в `Container` вовсе.

- [ ] **Step 4: `uv run pytest -q` — существующие тесты не меняются**
- [ ] **Step 5: Commit** `feat(api): judge answers out of band, never in the stream`

---

### Task 6: API и UI

**Files:**
- Modify: `apps/api/src/app/adapters/api/lab.py`, `sessions.py`
- Modify: `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md` (сначала!)
- Modify: `apps/web/src/api/client.ts`, `apps/web/src/components/ParetoPanel.tsx`, `apps/web/src/index.css`

- [ ] **Step 1: Строки в чеклист**

| Key | String |
|-----|--------|
| `col_quality` | Качество |
| `hint_quality` | Оценка ответов судьёй, 0–100%. В скобках — сколько прогонов оценено |
| `formula_summary` | *обновить*: Score = качество (или успех, пока оценок мало) ÷ время_ответа ÷ cost |

- [ ] **Step 2: API** — `avg_quality` и `judged_n` в элементах `models`; `quality_score`, `quality_model_id` в трейсах. Формы:

```jsonc
{"model_id": "x", "n": 12, "success_rate": 0.92, "avg_quality": 0.81, "judged_n": 7,
 "p50_ttft_ms": 800.0, "p50_total_ms": 4100.0, "avg_cost_proxy": 1.0, "score": 0.19}
```

- [ ] **Step 3: Колонка** между «Успех» и «p50, с»: процент, `—` при `null`, `judged_n` в `title` ячейки. На ≤480px прятать «Успех», когда «Качество» заполнено, — тем же приёмом, которым уже прячется `N`.

- [ ] **Step 4: Проверить** `npx tsc -b --noEmit`, `npm run lint` (базовая линия — 7 warnings), и на живом стенде: без `JUDGE_MODEL` таблица выглядит ровно как сегодня.

- [ ] **Step 5: Commit** `feat(web): quality column in the model ranking`

---

### Task 7: Верификация и документация

- [ ] **Step 1:** `uv run pytest -q && uv run ruff check src tests && uv run mypy src`; web `tsc` + `lint`
- [ ] **Step 2:** Интеграционный прогон на одноразовом Postgres с `RUN_INTEGRATION=1`
- [ ] **Step 3:** Живой стенд: `JUDGE_MODEL` задан → после нескольких сообщений в колонке появляются проценты; `JUDGE_MODEL` пуст → таблица идентична сегодняшней
- [ ] **Step 4:** Имена переменных в `.env.example` и `docs/env-local.md` (**только имена**)
- [ ] **Step 5:** Отметить D.3 в мастер-плане и в `deferred-features.md`
- [ ] **Step 6: Commit** `docs: judge env knobs and phase D.3 status`

---

## Self-review

- **Покрытие спеки:** вне-запросный судья — Task 5; сэмплирование — Task 2; рубрика в YAML — Task 3;
  запрет самооценки — Task 3; `None` вместо нуля — Task 2; ветвление Score — Task 4;
  колонка и подсказка — Task 6; риски из спеки закрыты тестами Tasks 2, 3, 5.
- **Плейсхолдеров нет:** шаги с кодом несут код. Tasks 4–5 описывают тесты словами там, где
  они опираются на существующие фикстуры (`tests/unit/fakes.py`) — исполнитель читает соседний
  файл, а не догадывается.
- **Согласованность типов:** `QualityVerdict` (1) → `parse_verdict` (2) → `LLMAnswerJudge` (3)
  → колонки и `ModelAggregate.avg_quality`/`judged_n` (4) → планировщик (5) → JSON и колонка (6).
- **Главный риск, принятый сознательно:** оценивается выборка, а не всё. Поэтому `judged_n`
  показывается рядом с числом, а Score не трогает качество, пока выборка мала.
