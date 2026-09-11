# Modular Context Strategies (Day 10) — Design Spec

**Date:** 2026-09-11  
**Status:** Approved (Approach A — domain strategy module)  
**Depends on:** Day 7 dialogs, Day 8 token meter, Day 9 compression  
**Challenge:** `challenges/10-context-strategies/` (Video + Code)

## Goal

Один взаимоисключающий `context_mode` — все режимы сборки **равноправны** (Day‑9 — просто режим `compress`, не отдельный параллельный тумблер):

| Mode | Что делает |
|------|------------|
| `none` | **Без эффектов** — полная история как есть (+ только Day‑8 fit по лимиту токенов) |
| `compress` | Day‑9 rolling summary + recent N |
| `sliding` | Только последние N |
| `facts` | Sticky KV (LLM-extract) + последние N |

**Branching** — не mode сборки: checkpoint → fork в новый dialog → независимые ветки (можно поверх любого mode).

Сравнение на сценарии «собираем ТЗ» (10–15 реплик): качество, стабильность, токены, UX. Архитектура модульная — тот же `assemble_context` для agent и (позже) любого chat.

## Non-goals

- Замена поведения `compress` (логика Day‑9 остаётся той же)  
- Tree-inside-one-row branching  
- Tiktoken / точный биллинг  
- Полная миграция main chat на strategies в том же PR (достаточно модуля + agent consumer; chat — follow-up)

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Strategy switch | Один enum `context_mode` — ровно один режим за раз |
| Day‑9 | Значение `compress` в том же enum; поведение как сейчас |
| UI | Один selector; отдельный checkbox «Сжимать историю» убираем / мапится в `compress` |
| Facts update | LLM-extract после user turn |
| Branching | Fork = **новый** `AgentDialog` (prefix copy); ортогонально mode |
| Architecture | Domain `assemble_context` + pluggable strategies (Approach A) |

## Architecture

```text
domain/context_strategies/
  types.py          # ContextMode, ContextState, AssemblyResult, StrategyMeta
  assemble.py       # assemble_context(messages, mode, state, opts) -> AssemblyResult
  sliding.py
  facts.py          # format facts block; merge helpers (extract prompt is application)
  compress.py       # thin adapter over existing context_compress.py OR re-export
```

**Consumer-agnostic contract:**

```text
assemble_context(
  messages: list[MessageLike],   # role + content (+ id optional)
  mode: ContextMode,             # none | compress | sliding | facts
  state: ContextState,           # summary_text, summary_until_count, facts: dict[str,str]
  opts: { recent_keep, summarize_every, ... }
) -> AssemblyResult {
  history: list[MessageLike],    # turns sent to LLM (excl. current user)
  system_extra: str,             # summary and/or facts blocks (empty if none)
  state_patch: ContextState,     # may be unchanged; compress/facts updaters apply later
  meta: StrategyMeta             # for API/UI meters
}
```

Branching is **not** an assembly mode: it is a repository/use-case operation `fork_dialog(...)`.

```text
load dialog → (optional facts extract / compress refresh) → assemble_context
  → merge system(definition + system_extra) → Day-8 fit_history_to_budget
  → LLM → append full turns to stored messages → save state
```

Full message log always stays in Postgres for UI; strategies only change **what is sent**.

## Modes

### `none` (без эффектов)

Полная сохранённая история в запрос; никакого window / summary / facts.  
Единственное урезание — Day‑8 `fit_history_to_budget`, если задан лимит контекста.  
UI label: **Нет** / «Без эффектов». Default.

### `compress` (бывший Day 9)

Тот же режим, что Day‑9: rolling LLM summary + recent N; поля `summary_text` / `summary_until_count`.  
Не «особый» путь рядом с другими — обычная ветка `assemble_context`.  
Compat: старый `compress: true` без `context_mode` → `context_mode=compress`.

### `sliding`

- Keep last `recent_keep` messages (default **8** for Day‑10 demos; clamp 2…40).  
- Drop older from the **request** only.  
- No summary, no facts injection.  
- Meta: `window_kept`, `window_dropped`, token estimates raw vs windowed.

### `facts`

- Persist `facts: dict[str, str]` on dialog (JSONB).  
- After each **user** message (while mode=facts): LLM-extract call updates facts (merge keys; empty value deletes key; preserve unrelated keys).  
- Request: `system_extra` = formatted facts block + history = last `recent_keep` messages.  
- Suggested keys (prompt hint, not schema): `goal`, `constraints`, `preferences`, `decisions`, `agreements`, free-form others.  
- Meta: `facts_count`, `facts_updated`, token estimates.

Extract prompt returns strict JSON object only. On parse failure: keep previous facts, set `facts_updated=false` (main run still proceeds).

### Branching (fork)

`POST /api/v1/agent-workshop/dialogs/{id}/fork` (or by-draft):

Request:

```json
{
  "from_message_id": "<id in messages>",
  "client_draft_id": "<new draft id for branch>",
  "label": "optional branch name"
}
```

Behavior:

1. Authz: visitor owns source dialog.  
2. Find message index by `from_message_id`; copy `messages[:index+1]`.  
3. Copy definition fields + `facts` + `summary_*` as of fork time.  
4. Create new dialog row with new `client_draft_id` (unique per visitor).  
5. Return new dialog DTO.

UI: «Checkpoint» on a message → create two forks (A/B) or fork twice with labels → switch active `dialogId` / draft. Each branch continues independently.

## Persistence

Migration `009_agent_dialog_facts_branch.py` (name flexible):

| Column | Type | Role |
|--------|------|------|
| `facts` | JSONB, default `{}` | Sticky KV for `facts` mode |
| `parent_dialog_id` | UUID nullable FK | Optional lineage for UI |
| `branch_label` | text nullable | Display name |
| `forked_from_message_id` | text nullable | Checkpoint message id |

Clear dialog: wipe messages, summary fields, **and** facts (same as Day‑9 clear). Forked children are separate rows (not auto-deleted).

## API

### Run request

```json
{
  "context_mode": "none | compress | sliding | facts",
  "recent_keep": 8,
  "summarize_every": 10,
  "compress": false
}
```

- Источник истины: `context_mode` (ровно один).  
- Compat: только `compress: true` без mode → `compress`; если оба заданы и конфликтуют → 422.

### Run response extras

```json
{
  "context_strategy": {
    "mode": "sliding",
    "recent_kept": 8,
    "dropped": 12,
    "facts": {},
    "facts_updated": false,
    "tokens_raw_est": 900,
    "tokens_strategy_est": 320,
    "summary_used": false
  },
  "tokens": { "...Day 8..." },
  "compression": null
}
```

При `mode=compress` заполняем и `context_strategy`, и прежний блок `compression` (чтобы старый UI/клиенты не ломались).

### Dialog GET

Expose `facts`, `parent_dialog_id`, `branch_label`, `forked_from_message_id` alongside messages/summary.

## UI (Agent Workshop solo)

- Один selector **Контекст:** `Без эффектов` | `Сжатие` | `Окно` | `Facts`.  
- Default: `none` (без эффектов).  
- Params: `recent` (sliding/facts/compress), `every` (только compress).  
- Panel **Facts** при mode=facts.  
- Branch UI отдельно: checkpoint → fork A/B → переключение dialog (mode у каждой ветки свой).  
- Meter: `сырой → strategy` только если mode ≠ `none`.

## Challenge / video

Folder: `challenges/10-context-strategies/`

Scenario (same script × modes): build a short ТЗ over 10–15 turns (goal, stack, constraints, deadline, then recall probe).

Compare:

| Mode | Expect |
|------|--------|
| sliding | Меньше токенов; может забыть ранние детали ТЗ |
| facts | Держит KV; умеренные токены |
| compress | Summary-режим (равноправный peer) |
| branching | Две ветки ТЗ от checkpoint; switch работает |

Deliverable: `run.py` + Playwright `RECORD_ONLY=10` + `challenge-10.mp4` + RESULTS comparison.

## Testing

- Unit: `assemble_context` for sliding/facts/none; compress adapter still matches Day‑9 plans.  
- Unit: facts merge/parse; fork copies prefix + facts.  
- Application: `run_agent_with_dialog` with FakeLLM for sliding + facts extract + main.  
- No real LLM keys in CI.

## Rollout

1. Domain module + migration + agent workshop wire.  
2. UI selector + facts + fork.  
3. Challenge + deploy + video.  
4. Follow-up (optional): call `assemble_context` from `application/chat.py` with same modes.
