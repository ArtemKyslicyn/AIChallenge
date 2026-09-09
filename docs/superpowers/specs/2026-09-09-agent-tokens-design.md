# Agent Token Meter (Day 8) — Design Spec

**Date:** 2026-09-09  
**Status:** Approved for implementation  
**Depends on:** Day 6 `run_agent` / Day 7 `agent_dialogs`  
**Challenge:** `challenges/08-tokens/` (Video + Code)

## Goal

Считать токены агента (приблизительно) для **текущего запроса**, **истории диалога** и **ответа модели**; показывать рост стоимости/токенов; при переполнении бюджета контекста **обрезать старую историю** и явно предупреждать в UI.

## Counting

Формула платформы (как чат / Performance Studio):

```text
tokens ≈ max(1, len(text) // 4)   # empty → 0
```

Поля в `POST /api/v1/agent-workshop/run` response:

| Field | Meaning |
|-------|---------|
| `tokens.request` | system + история **после** обрезки + текущий user |
| `tokens.history_before` | user/assistant история **до** обрезки |
| `tokens.history_after` | то же после обрезки |
| `tokens.completion` | ответ модели |
| `tokens.total` | request + completion |
| `cost_proxy` | грубая шкала по `model_id` (как challenge runners) |
| `truncation.applied` | bool |
| `truncation.dropped_messages` | int |
| `truncation.dropped_tokens_est` | int |

## Budget / overflow

```text
budget = context_limit - reserve_for_completion
reserve = min(max_tokens or 512, context_limit // 4)
```

- Default `context_limit`: **8192** (override: request `context_limit`, clamp 64…128000 — для демо переполнения).
- Если `tokens(system+history+user) > budget`: удалять **самые старые** пары/сообщения из history, пока не влезет (system + текущий user всегда остаются).
- В LLM уходит только обрезанный хвост; в Postgres по-прежнему пишется полный нарастающий лог (как Day 7), но для следующего turn снова применяется fit.

## UI

Solo agent workshop: после ответа — блок «Токены» (request / history / completion / total + cost_proxy). При `truncation.applied` — жёлтый баннер «История обрезана: N сообщений (~T tok)».

## Challenge 08

Сценарии: короткий диалог → длинный → `context_limit` занижен → truncate. Видео Playwright + `run.py`.

## Non-goals

tiktoken, точный биллинг провайдера, SSE token frames для agent run, отказ 413 вместо truncate.
