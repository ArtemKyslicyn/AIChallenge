---
name: aichallenge-llm
description: >-
  LLM port, OpenAI-compatible adapter, ModelRouter failover, SSE model
  attribution, and /llm/complete probe for AIChallenge. Use when changing
  streaming, providers, OpenRouter/DeepSeek, model chain, or model_id UI/API.
---

# AIChallenge LLM

## Port

```text
LLMProvider.stream_chat(...) -> AsyncIterator[TokenChunk]
LLMProvider.complete_chat(...) -> CompletionResult
```

Both results must expose the **resolved** `model_id` that actually answered.

## Adapters

- `OpenAICompatibleProvider` — single client via `LLM_BASE_URL` + `LLM_API_KEY`
- `FakeLLMProvider` — tests/CI without keys
- DeepSeek / OpenRouter = config, not new domain types

## ModelRouter

- Ordered chain: env `LLM_MODEL_CHAIN` and/or `configs/llm_models.yaml`
- Failover on 429 / quota / payment-required / timeout → next model
- Mark exhausted models with TTL (in-process v1; Redis later behind same API)
- Scenario `preferred_model: auto` uses router; explicit id pins when possible

## Client visibility (required)

Assistant replies must show which model answered:

- Persist `Message.model_id` for assistant messages
- SSE: early `event: model`, update on failover, include `model_id` in `message_end`
- History API returns `model_id`
- `POST /api/v1/llm/complete` returns `model_id`
- Web UI shows model label on assistant bubbles (and probe)

## Probe

- `POST /api/v1/llm/complete` — same provider/router, no DB by default
- Gated by `LLM_PROBE_ENABLED`

## Logging

Log model id and failover reason. Do not log API keys or full prompts in prod defaults.
