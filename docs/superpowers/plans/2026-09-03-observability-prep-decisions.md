# Prep decisions — Observability → Prefs → Routing (locked 2026-09-03)

**Status:** binding contract for P0/P1/P2 executors.
**Master:** [2026-09-03-observability-routing-master.md](./2026-09-03-observability-routing-master.md)

Подпланы описывают *что* делать. Этот файл фиксирует *как* — после чтения реального кода.
Где подплан противоречит этому файлу, **выигрывает этот файл** (расхождения помечены ⚠️).

---

## D1 ⚠️ Attempts journal: per-request, не instance buffer

P1 Task 2 предлагает `self._last_attempts` / `take_last_attempts()`. **Так делать нельзя:**
`ModelRouter` живёт в `Container` как синглтон и обслуживает параллельные SSE-запросы —
буфер на инстансе перемешает попытки двух чатов.

**Контракт:** коллектор передаётся вызывающим, по одному на запрос.

```python
# app/domain/ports.py — ChatRouter
def stream_chat(
    self,
    messages: list[ChatMessage],
    preferred_model: str = AUTO_MODEL,
    *,
    generation: GenerationParams | None = None,
    attempts: list[AttemptRecord] | None = None,
) -> AsyncIterator[TokenChunk]: ...

async def complete_chat(
    self, ..., attempts: list[AttemptRecord] | None = None
) -> CompletionResult: ...
```

- Дефолт `None` обязателен: `llm_probe.py` и media-probe в `chat.py` вызывают роутер без коллектора.
- `ModelRouter` и `TieredModelRouter` реализуют оба; `TieredModelRouter` просто пробрасывает
  один и тот же список в каждый tier — записи из всех tier'ов лежат в одном журнале по порядку.
- Запись добавляется: на каждом retryable-фейле (`ok=False`, `reason=_fail_reason(exc)`,
  `error_kind=exc.kind`) и один раз на успехе (`ok=True`, `ttft_ms` от старта попытки до первого чанка).
- Mid-stream abort (`LLMStreamAbortedError`) тоже пишет запись `ok=False, reason="aborted"`.
- `attempts` — доменный тип, роутер (адаптер) импортирует `app.domain.tracing`. Слои не нарушены.

## D2 Где считается время

В `application/chat.py`, `time.monotonic()` (stdlib — слой не нарушает):

- `started = monotonic()` перед первым обращением к роутеру (**до** media-probe, чтобы `total_ms`
  честно включал tool-round);
- `ttft_ms` — по первому `TokenEvent`, который реально ушёл читателю (включая media-prefix);
- `total_ms` — в `finalize()`.

## D3 Где сохраняется trace

Внутри `finalize()` в `chat.py`, после `uow.commit()` сообщения. Одна точка покрывает ok / abort /
exhausted / provider-error, потому что все они идут через `finalize`.

```python
async def finalize(model_id: str | None, *, marker: str = "") -> str:
    ...  # existing message write + commit
    await _save_trace(status=...)   # never raises
```

- `traces: RunTraceRepository | None = None` — новый kwarg `send_user_message_and_stream`.
- Ошибка записи трейса **не должна ломать SSE**: `try/except Exception` → `logger.warning` →
  `await uow.rollback()` (иначе сломанная транзакция утянет за собой следующий commit).
- ⚠️ **Disconnect не пишет trace в v1.** Клиент отвалился → `finalize` не выполняется, спасательная
  запись в `sessions.py::_rescue_unsaved` трогает только сообщение. Это осознанный компромисс,
  задокументировать в подплане, не чинить сейчас.
- `status`: `ok` | `aborted` (LLMStreamAbortedError) | `exhausted` (LLMExhaustedError) |
  `error` (LLMProviderError и пустой ответ).

## D4 Settings (новые имена; значения — никогда в репозиторий)

```
RUN_TRACE_ENABLED=true                  # run_trace_enabled: bool = True
MODEL_COST_PROXY_JSON=                  # model_cost_proxy_json: str = ""  → dict[str, float]
FEEDBACK_DOWN_RATE_THRESHOLD=0.6        # float
FEEDBACK_MIN_VOTES=5                    # int
FEEDBACK_PENALTY_TTL_SECONDS=86400      # int
FEEDBACK_PENALTY_REFRESH_SECONDS=60     # int — кэш агрегатов в процессе
FEEDBACK_EXPORT_ENABLED=false           # bool — gate на /lab/preference-export
FEEDBACK_EXPORT_INCLUDE_CONTENT=false   # bool
```

`Settings.model_cost_proxy()` парсит JSON один раз, при битом JSON — `logger.warning` и `{}`
(конфиг не должен ронять API). Неизвестная модель → `cost_proxy = None`, а не 1.0.

## D5 Auth новых эндпоинтов (спека это не дозакрыла)

| Endpoint | Доступ | Почему |
|----------|--------|--------|
| `GET /api/v1/lab/pareto` | открыт, как `/lab/presets` | только агрегаты по `model_id`, PII нет |
| `GET /api/v1/lab/feedback-stats` | открыт | то же |
| `GET /api/v1/lab/preference-export` | `VisitorHash` **и** `FEEDBACK_EXPORT_ENABLED=true`, иначе 404 | построчный дамп ссылается на конкретные сообщения |
| `GET /api/v1/sessions/{id}/traces` | `AuthorizedSession` (существующий dep) | чужие сессии не видны |
| `POST /api/v1/messages/{id}/feedback` | `X-Session-Token` сообщения (см. D6) | одна сессия — свои сообщения |

`hours` во всех lab-роутах: `Query(24, ge=1, le=720)`.

## D6 Авторизация POST feedback

`require_session` завязан на `session_id` в пути, здесь его нет. В `adapters/api/feedback.py`:
message → `session_id` → `SqlAlchemySessionRepository.get` → сравнить `access_token` с заголовком.
Несовпадение токена, отсутствующее сообщение и чужая сессия дают **одинаковый 404**
(тот же принцип, что и в `require_session`). Не-assistant сообщение → 400.

## D7 Penalty применяется как переупорядочивание, не как бан

⚠️ Спека допускает «treat as temporarily exhausted». Выбрано **мягкое**: оштрафованные модели
уезжают **в конец** списка кандидатов внутри `_candidates`, но не исчезают — иначе плохой день
одной модели может оставить чат вообще без цепочки. Явный pin (`preferred_model`) остаётся первым
всегда.

```python
# adapters/llm/feedback_penalties.py
class FeedbackPenaltyCache:
    def is_penalized(self, model_id: str) -> bool: ...        # sync, читает кэш
    async def refresh(self, repo: FeedbackRepository) -> None: ...  # no-op пока TTL жив
```

`ModelRouter(..., penalties: FeedbackPenaltyCache | None = None)`; `_candidates` остаётся
синхронным. Кэш живёт в `Container`, `refresh` вызывается один раз перед стримом
в `sessions.py::send_message` (`try/except` — сбой обновления не блокирует чат).

## D8 Агрегация — в Python, с потолком

`aggregate()` тянет строки окна `ORDER BY created_at DESC LIMIT 5000` и считает p50/успех в Python.
Потолок обязателен: без него ручка на большом окне читает всю таблицу. Документировать лимит
в ответе не нужно, достаточно комментария в коде.

## D9 Формы ответов API (frontend строит типы по ним дословно)

```jsonc
// GET /api/v1/lab/pareto?hours=24
{
  "formula": "score = успех ÷ время_ответа ÷ cost",
  "hours": 24,
  "models": [
    {"model_id": "x", "n": 12, "success_rate": 0.92, "p50_ttft_ms": 800.0,
     "p50_total_ms": 4100.0, "avg_cost_proxy": 1.0, "score": 0.22}
  ]
}

// GET /api/v1/lab/feedback-stats?hours=168
{"hours": 168, "models": [{"model_id": "x", "ups": 4, "downs": 6, "down_rate": 0.6, "penalized": true}]}

// POST /api/v1/messages/{id}/feedback  body {"value": "up"|"down"}
{"message_id": "...", "value": "up"}

// GET /api/v1/sessions/{id}/traces
{"traces": [{"message_id": "...", "resolved_model_id": "x", "status": "ok",
             "ttft_ms": 800, "total_ms": 4100, "attempts": [{"model_id": "y", "ok": false, "reason": "http_429"}],
             "created_at": "..."}]}
```

`p50_*` и `avg_cost_proxy` могут быть `null` — UI обязан это переживать (прочерк, не `NaN`).

## D10 ⚠️ Web: у живого ответа нет id сообщения

`Chat.tsx` заводит турн с `id: "reply-<ts>"`; серверный id приходит только в `message_end`.
FeedbackStrip нужен настоящий id, поэтому:

- `Turn` в `types.ts` получает `messageId?: string | null`;
- `toTurn(message)` ставит `messageId: message.id` для истории;
- обработчик `message_end` ставит `messageId: event.message_id`;
- `FeedbackStrip` рендерится только при `role === "assistant" && messageId && !streaming`.

Это ровно тот «не показывать оценку посреди стрима», который требует H5 чеклиста.

## D11 Web: mutex трёх панелей

`resultsOpen`/`debugOpen` в `Chat.tsx` схлопываются в
`activeFloat: "debug" | "results" | "models" | null`. `DebugFloat` и `LabResultsFloat` уже
контролируемые (`open` + `onOpenChange` / `onClose`) — их сигнатуры менять не нужно.
`ModelsFloat` повторяет паттерн `DebugFloat`: FAB с `aria-expanded`/`aria-controls`,
Escape закрывает и возвращает фокус на FAB.

## D12 Порядок волн (кто чего ждёт)

| Волна | Трек | Файлы |
|-------|------|-------|
| 1 | P1 backend (Tasks 1–6) | `apps/api` |
| 1 | P0 Tasks 2–3 (mutex + ModelsFloat shell) | `Chat.tsx`, `ModelsFloat.tsx`, `index.css` |
| 2 | P2 backend (Tasks 1–6) | `apps/api` |
| 2 | P0 Task 4 (ParetoPanel + client) | `ParetoPanel.tsx`, `client.ts` |
| 3 | P0 Tasks 5–6 (FeedbackStrip + FeedbackStatsPanel) | `Turn.tsx`, `types.ts`, `client.ts` |
| 4 | Phase C (verify, heuristic gate, env docs, demo script) | tests + docs |

P1 и P2 оба правят `router.py`, `ports.py`, `models.py`, `lab.py`, `deps.py` — поэтому строго
последовательно, не параллельно.

## D13 Definition of done для каждой волны

- `cd apps/api && uv run pytest -q` — зелёный (интеграционные скипаются без `RUN_INTEGRATION=1`)
- `uv run ruff check src tests && uv run mypy src` — чисто (mypy strict)
- `cd apps/web && npx tsc -b --noEmit && npm run lint` — чисто
- Коммит на каждую задачу подплана, сообщения — как в подплане
- Никаких значений секретов; `.env` не читать и не коммитить
