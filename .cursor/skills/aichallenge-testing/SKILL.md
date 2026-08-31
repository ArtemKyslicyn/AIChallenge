---
name: aichallenge-testing
description: >-
  Testing strategy for AIChallenge API and web: FakeLLMProvider, use-case
  units, Postgres integration, SSE contract. Use when writing or changing
  tests under apps/api/tests or apps/web.
---

# AIChallenge Testing

## Priority

1. **Application unit tests** — use cases + `FakeLLMProvider` (no network, no keys)
2. **API integration** — real Postgres (Testcontainers or Compose test profile)
3. **SSE contract** — at least one test for `model` → `token`* → `message_end` (or `error`)
4. **Router failover** — unit test: first model fails with 429 → second model used; `model_id` is the second

## Rules

- Never require a real `LLM_API_KEY` in CI
- Do not assert on secret values
- Prefer testing ports/fakes over mocking SQLAlchemy internals
- When adding an endpoint, add or extend the matching test layer above
