# First Agent (Day 6) — Design Spec

**Date:** 2026-09-07  
**Status:** Implemented (v1 + Day 6.1 client team)  
**Depends on:** `ChatRouter` / `GenerationParams`, probe-style LLM path, web App shell (no react-router)  
**Challenge format:** Video + Code (`challenges/06-first-agent/`)  
**Frontend skill:** `.cursor/skills/aichallenge-frontend/SKILL.md`  
**Architecture skill:** `.cursor/skills/aichallenge-architecture/SKILL.md`

## Goal

Реализовать **первого агента** как отдельную **серверную инкапсуляцию** настройки и вызова LLM: `AgentDefinition` (system prompt, model, temperature, max_tokens, …) + application use case `run_agent`. Снаружи HTTP/UI/challenge видят только результат (`content` + обязательный `model_id`).

В UI — отдельный workspace **«Агенты»** (shell mode), где можно собрать definition, прогнать **одиночные** запросы и (Day 6.1) оркестрировать **пачку** агентов на клиенте. Это не multi-turn chat с серверной памятью и не вкладка в «Модели».

**Disambiguation:** product UI «Агенты» ≠ coding agents (`AGENTS.md`) ≠ media **agent loop** (tool rounds in chat). В коде нет bare type `Agent` — только `AgentDefinition` + `run_agent`.

## Non-goals (Day 6 / v1)

- Визуальный editor графа / заморозка HTTP-контракта «под граф»
- Postgres-таблица агентов или server-side history диалогов
- Multi-turn memory внутри одного agent run (история реплик в UI — только лог независимых прогонов; handoff/roundtable собирают текст на клиенте)
- Tools / function-calling внутри agent run
- Замена основного чата или Scenario YAML
- Streaming SSE для agent run (`complete_chat` → JSON)
- Отдельный react-router `/agents`
- Второй YAML-tree `configs/agents/` (пресеты — на клиенте)
- Domain-слой, который сам вызывает `ChatRouter`
- Server-side batch/orchestration endpoint (клиент вызывает N× `POST …/run`)

## Day 6.1 — Client team orchestration

Опираясь на паттерны AutoGen / CrewAI / handoff (parallel fan-out, sequential chain, peer roundtable):

| Mode | Behavior |
|------|----------|
| Параллельно | Одна задача → все выбранные агенты сразу |
| Цепочка | A → B → C; следующий получает handoff с ответом предыдущего |
| Обсуждение | Раунд 1 параллельно; раунд 2 каждый комментирует остальных |

**UX (Day 6.1 pass):** сегмент **«Один агент» | «Команда»** (default solo). В solo — личный compose, без team bar/чекбоксов. В team — состав chips (+ порядок ↑↓ для цепочки), одна задача, ответы в ленте команды; личный лог только brief-статус. HTTP без изменений.

## Locked decisions

| Topic | Choice |
|-------|--------|
| Scope | Definition + workshop + runs; client team modes (Day 6.1); graph editor — later |
| Encapsulation | Application `run_agent` + domain `AgentDefinition` (pure validate/clamp only). HTTP не зовёт `/llm/complete` для этой фичи |
| Dialog semantics | **Stateless runs.** UI transcript = журнал независимых `run` (каждый: definition + один user message). Подпись: «Каждый вопрос — отдельный прогон» |
| Storage | Черновики в **localStorage**; run body = полный `definition` (ephemeral) |
| Shell UX | Topbar **`Чат \| Агенты`**. В `agents`: **нет** SessionSidebar, **нет** «Новый чат», **нет** float-dock |
| Models float | Без изменений |
| Boot | Mode `agents` **доступен без** успешного `ensureSession` (chat boot остаётся как есть) |
| Transport | `POST /api/v1/agent-workshop/run` → `{ content, model_id }` |
| Auth | Как probe: **session не обязателен**; клиент шлёт `X-Visitor-Id` (rate limit + analytics) |
| Kill switch | `AGENTS_RUN_ENABLED` (env; default true local). Disabled → тот же error family, что probe (`404` + code) |
| Limits | `system_prompt` и `message` ≤ chat `MAX_MESSAGE_CHARS`; `temperature`/`max_tokens` bounds как probe; per-visitor hourly run cap |
| Errors | Shared `{ error: { code, message } }`: validation **422**, provider **502**, exhausted **503**, disabled **404** |
| Persistence of runs | Нет Session/Message/RunTrace |
| Observability | Fail-open analytics `agent_run_completed` / `agent_run_failed` (`model_id`, latency, sizes) — без полного system_prompt |
| Attribution | Resolved `model_id` обязателен |
| Naming (code) | `AgentDefinition`, `run_agent`, module/router `agent_workshop` |
| Naming (UI) | «Агенты», «Инструкция агента», «Как отвечает» |
| Presets | 1–2 **client-side** presets only (no GET / no server YAML in Day 6) |
| Deep link | Read `?shell=agents` (or `#agents`) once on boot; also persist `sessionStorage` `aichallenge.shell_mode` |
| Scenario vs workshop | Scenario = persona сессии чата; workshop = ephemeral definition без Session rows |

## Product intent (UX)

| Persona | Job | Surface |
|---------|-----|---------|
| Ученик Day 6 | Увидеть: definition + `run_agent` → только результат + `model_id` | Workspace «Агенты» |
| Обычный чат | Не мешать ×T / ×4 / Модели | Workspace «Чат» |

Не цель: второй чат с памятью; вкладка в Модели; 4-й FAB; dimmed-but-clickable sidebar.

## Information architecture

```text
App
├── topbar
│     ├── [Чат | Агенты]     ← primary shell (role=group + aria-pressed)
│     ├── brand
│     └── chat-only: History (icon) — «Новый чат» убрать из topbar (есть в sidebar)
├── mode=chat
│     ├── SessionSidebar
│     ├── Chat + float-dock (unchanged)
│     └── session boot gate (ensureSession) as today
└── mode=agents
      └── AgentWorkshop only (no chat sidebar, no float-dock, no session required)
            desktop: library rail | builder | run log
            mobile:  run log primary; «Настройки» → sheet (не второй peer-segment)
```

**Empty-state (чат):** не новый chip в кучу. Одна secondary-ссылка: «Собрать агента (урок 6)» → `shell=agents`. Media/×T chips по возможности свернуть под «Ещё примеры» (минимум: не добавлять третью группу chips).

## Domain / application

### Domain (`AgentDefinition`)

```text
AgentDefinition
  name: str                    # UI/drafts only; optional on run DTO
  system_prompt: str           # required, non-empty, max_length
  preferred_model: str         # "auto" | concrete id
  temperature: float | None
  max_tokens: int | None
```

Pure helpers only: validate non-empty fields, clamp ranges if needed. **No** `ChatRouter` import in domain.

### Application

```text
run_agent(*, definition: AgentDefinition, message: str, router: ChatRouter)
  → domain validate
  → ChatMessage[SYSTEM, USER]   # assembly owned here
  → GenerationParams via generation_from_api(temperature, max_tokens, …)
  → router.complete_chat(..., preferred_model=..., generation=...)
  → CompletionResult (content, model_id)  # reuse; HTTP may wrap as AgentRunResponse
```

HTTP adapter: DTO → `AgentDefinition` → `run_agent`. Do not fork a second LLM stack; sibling to `complete_probe`.

`apply_generation_to_messages`: call only if prompt_controls exist; Day 6 typically builds `GenerationParams(temperature, max_tokens)` only.

## API

```http
POST /api/v1/agent-workshop/run
Content-Type: application/json
X-Visitor-Id: <recommended>

{
  "definition": {
    "name": "Редактор",
    "system_prompt": "Ты краткий редактор. Правишь стиль, не смысл.",
    "preferred_model": "auto",
    "temperature": 0.3,
    "max_tokens": 512
  },
  "message": "Перепиши: ну короче это типа важно"
}
```

```json
{
  "content": "…",
  "model_id": "provider/model-id"
}
```

| Case | Status | Notes |
|------|--------|-------|
| Validation / size | 422 | Same envelope as chat/probe |
| Provider error | 502 | RU message |
| Exhausted | 503 | RU message |
| `AGENTS_RUN_ENABLED=false` | 404 | probe-disabled-style code |
| Visitor rate limit | 429 | Optional; client retries like prod_client |

Wire: `application/agent_run.py` + `adapters/api/agent_workshop.py` (not dumped into `llm.py`).

## UI / UX detail

### Topbar mode switch

- `role="group"` + `aria-pressed` (не смешивать с `tablist` без полного tabs pattern).
- `aria-live` polite: «Режим: Агенты».
- `sessionStorage` + one-shot `?shell=agents`.
- While agent run busy: disable shell switch **or** require Stop first; leaving agents cancels AbortController + status «Запрос отменён».
- Chat in-flight: switching to agents does not abort chat unless we later decide otherwise (Day 6: leave chat running; workshop independent).

### AgentWorkshop

**Desktop**

```text
┌─ Агенты ──────────────────────────────────────────────┐
│ Библиотека: Пресеты | Мои     [+ Новый агент]         │
├───────────┬─────────────────────┬─────────────────────┤
│ список    │ Кто отвечает        │ Прогоны             │
│           │ Инструкция агента   │ (лог одиночных run) │
│           │ Как отвечает:       │ model_id badge      │
│           │  model · temp · max │ [input] [Отправить] │
│           │ «Сохранено · браузер»│ [Стоп] when busy   │
└───────────┴─────────────────────┴─────────────────────┘
```

**Mobile:** full-screen run log; sticky bar with agent name + «Настройки» → sheet (builder + library). **No** peer `Сборка | Диалог` segment equal to shell mode.

**Draft lifecycle**

- Autosave debounce; badge «Сохранено · только в этом браузере».
- Switch draft / apply preset: **clear run log** (confirm if log non-empty).
- Preset apply: «Создать черновик из пресета» — never silent overwrite of named draft.
- Actions: Новый · Переименовать · Удалить · Дублировать.
- Soft cap ~20: block new + ask delete/overwrite — **no silent LRU eviction**.
- First visit: seed one preset as active draft.
- Corrupted localStorage: reset to seed preset.

**Microcopy**

- Empty log: «Задай вопрос этому агенту. Каждый вопрос — отдельный прогон; ответ придёт с меткой модели.»
- Footer hint: «Диалог-лог не пишется на сервер (только настройки в браузере).»
- Busy: «Ждём ответ…»
- Error: «Не удалось получить ответ.» + server `message`
- Optional sessionStorage last N log lines keyed by `activeId` for F5 comfort (still not server history)

**Visual:** existing chat tokens; builder = identity («Кто отвечает»), not a clone of Performance Studio chrome. CTA «Отправить» (align with chat send). Debug float stays chat-only (document).

### localStorage

```text
aichallenge.agent_drafts.v1 = {
  activeId: string,
  drafts: [{ id, name, system_prompt, preferred_model, temperature, max_tokens, updatedAt }]
}
```

## Errors / limits (client)

| Case | Behavior |
|------|----------|
| Empty message / system_prompt | Prevent send + 422 if bypassed |
| Oversize | Prevent + 422 |
| LLM fail | Error in log; keep builder |
| Abort / Stop | No partial bubble; status cancelled |
| Rate / disabled | Same messaging family as probe |
| Double-submit | Disable Отправить while in-flight |

## Challenge (Video + Code) — parity with 04/05

`challenges/06-first-agent/`:

- `README.md` — UI: `?shell=agents` или topbar **Агенты** → пресет → вопрос → ответ + `model_id`; note Scenario vs workshop
- `prompt.txt` — fixed user message
- `run.py` — `POST /agent-workshop/run` via `_lib/prod_client.py` (`agent_run` helper), `results.json` + `RESULTS.md` (latency, model_id, …)
- `challenges/record` — `challenge-06` wait for bubble + model_id
- Deliverables: `.webm` / `.mp4` like 04/05

## Testing

- Unit: validate `AgentDefinition`; `run_agent` with **fake ChatRouter** → content + model_id; generation params forwarded
- API TestClient: happy path; 422 size/empty; disabled → 404 shape; exhausted → 503 if fake supports
- Assert path is **not** `/llm/complete`
- Web: draft roundtrip; switch draft clears log; visitor header on run; Stop/abort; Agents without session

## Success criteria

1. `run_agent` инкапсулирует assembly + LLM; наружу только результат + `model_id`
2. UI: `Чат | Агенты`; agents workspace без chat chrome; stateless run log
3. «Модели» float не раздут
4. Kill switch, size limits, error codes = platform norms
5. Challenge 06 parity with 04/05 artifacts
6. Domain-agnostic code names; no secrets in repo

## Implementation notes

- Settings: `AGENTS_RUN_ENABLED` in `.env.example` (name only) + `docs/env-local.md`
- Reuse `generation_from_api` / FakeLLM via DI
- Plan: `docs/superpowers/plans/2026-09-07-first-agent.md`
- Later graphs (if any) call application `run_agent` internally — public HTTP stays definition + single message
