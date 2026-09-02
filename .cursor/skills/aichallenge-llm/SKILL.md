---
name: aichallenge-llm
description: >-
  LLM port, OpenAI-compatible adapter, ModelRouter failover, SSE model
  attribution, and /llm/complete probe for AIChallenge. Use when changing
  streaming, providers, RouterAI/OpenRouter/DeepSeek, model chain, or model_id UI/API.
---

# AIChallenge LLM

## Port

```text
LLMProvider.stream_chat(...) -> AsyncIterator[TokenChunk]
LLMProvider.complete_chat(...) -> CompletionResult
```

Both results must expose the **resolved** `model_id` that actually answered.

## Adapters

- `OpenAICompatibleProvider` — single client via `LLM_BASE_URL` + resolved key
- Key resolution: `LLM_API_KEY` or, if empty, `ROUTERAI_KEY` (`Settings.resolved_llm_api_key()`)
- `FakeLLMProvider` — tests/CI without keys
- RouterAI / OpenRouter / DeepSeek = **config only**, no new domain types

## Default provider (prod / `.env.example`)

- `LLM_BASE_URL=https://routerai.ru/api/v1`
- Chain (quality/price balance; update docs when changing):

```text
deepseek/deepseek-v4-flash
qwen/qwen3-235b-a22b-2507
deepseek/deepseek-v3.2
google/gemini-2.5-flash
```

Cheaper alternative and other providers: comments in `.env.example`, details in `docs/env-local.md`.

## ModelRouter

- Ordered chain: env `LLM_MODEL_CHAIN` only (no YAML chain file — one source of truth)
- Failover on 429 / quota / payment-required / timeout / **404 (missing model)** / 5xx / transport blips → next model
- **Failover only before the first token.** After a token has been streamed, a provider failure raises
  `LLMStreamAbortedError`; the caller persists the partial text + `model_id` and ends with `event: error`.
  Never switch models mid-answer — it splices two different completions.
- Optional second provider tier (`LLM_FALLBACK_*`): tried after the primary chain is exhausted (or 401 on the tier)
- API keys are matched to the host (`OPENROUTER_API_KEY` only for openrouter.ai, `ROUTERAI_KEY` for routerai.ru)

## Client visibility (required)

Assistant replies must show which model answered:

- Persist `Message.model_id` for assistant messages
- SSE: early `event: model` (at most one per reply, since failover is pre-first-token), include `model_id` in `message_end`
- History API returns `model_id`
- `POST /api/v1/llm/complete` returns `model_id`
- Web UI shows model label on assistant bubbles (and probe)

## Probe

- `POST /api/v1/llm/complete` — same provider/router, no DB by default
- Gated by `LLM_PROBE_ENABLED`

## Logging

Log model id and failover reason. Do not log API keys or full prompts in prod defaults.
