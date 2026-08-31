# AI Chat Platform — Design Spec

**Date:** 2026-08-31  
**Status:** Approved for planning (pending user review of this document)  
**Approach:** Clean / hexagonal modular monolith

## 1. Goal

Build a scalable, domain-agnostic **AI chat platform** monorepo:

- Backend: Python (FastAPI), Clean/Hexagonal architecture, SOLID
- Frontend: React + TypeScript (Vite SPA)
- Infra: Docker Compose (api, web, Postgres)
- Secrets: never in git, never pasted into agent chat

Product intent (e.g. pre-visit dialogue) is **configuration only**. Code, package names, API, and default scenarios must not encode medical or role-specific domain language (`patient`, `doctor`, etc.).

## 2. Decisions (locked)

| Topic | Choice |
|-------|--------|
| Product shape | AI/chat platform; domain via scenarios later |
| Auth (v1) | Anonymous sessions; auth later (`user_id` nullable) |
| Streaming | SSE tokens |
| LLM | OpenAI-compatible port + adapter; DeepSeek/OpenRouter via config |
| Model selection | Ordered free-model chain with failover on quota/rate-limit |
| DB | PostgreSQL |
| Frontend | Vite + React + TypeScript SPA |
| Secrets | `.env` local + `.env.example`; Cloud/CI secrets injection |
| Backend shape | Modular monolith (not microservices in v1) |
| Scenarios | YAML files now; `ScenarioRepository` port → DB later |
| Session access | Create on visit + `access_token` in model (UI simple) |
| Architecture style | Clean/hexagonal layers |

## 3. Repository layout

```
/
├── apps/
│   ├── api/                      # FastAPI modular monolith
│   │   ├── src/app/
│   │   │   ├── domain/           # entities, VOs, ports
│   │   │   ├── application/      # use cases
│   │   │   ├── adapters/
│   │   │   │   ├── api/          # routers, schemas, SSE
│   │   │   │   ├── persistence/  # SQLAlchemy, repos
│   │   │   │   ├── llm/          # OpenAI-compatible, ModelRouter
│   │   │   │   └── scenarios/    # YAML ScenarioRepository
│   │   │   ├── core/             # settings, logging, DI
│   │   │   └── main.py
│   │   ├── tests/
│   │   ├── alembic/
│   │   ├── pyproject.toml        # uv
│   │   └── Dockerfile
│   └── web/                      # Vite + React + TS
│       ├── src/
│       ├── Dockerfile
│       └── nginx.conf
├── configs/
│   └── scenarios/                # generic YAML scenarios
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .cursorignore
├── AGENTS.md                     # agent rules: never read/paste .env
├── .cursor/rules/                # same constraint for Cursor
└── README.md
```

### Layer rules

- `domain` must not import FastAPI, SQLAlchemy, httpx, or framework code.
- `application` depends only on domain ports and entities.
- `adapters` implement ports and wire frameworks.
- Naming: `Session`, `Message`, `Scenario`, `Participant` — no domain leakage.

## 4. Domain model (v1)

### Session

- `id` (UUID)
- `access_token` (opaque secret)
- `scenario_id`
- `status` (`active` | `closed`)
- `created_at`
- `user_id` (nullable, unused in v1)

### Message

- `id` (UUID)
- `session_id`
- `role` (`user` | `assistant` | `system`)
- `content`
- `created_at`

### Scenario (config)

- `id`
- `system_prompt` (generic)
- `preferred_model` (`auto` or model id)

## 5. HTTP API (v1)

Base prefix: `/api/v1`. Session-scoped routes require header `X-Session-Token: <access_token>`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness |
| `POST` | `/sessions` | Create session (optional `scenario_id`) → `{id, access_token}` |
| `GET` | `/sessions/{id}` | Session metadata |
| `GET` | `/sessions/{id}/messages` | Message history |
| `POST` | `/sessions/{id}/messages` | User message; response is **SSE** stream of assistant tokens |
| `GET` | `/sessions/{id}/stream` | SSE reconnect / resume for an in-flight assistant message |
| `POST` | `/llm/complete` | Direct LLM probe (no session persistence by default) |

### Chat message flow

1. Client `POST /sessions/{id}/messages` with user content.
2. Server persists user message, creates pending assistant message id.
3. Response body is SSE: `token` events, then `message_end` (final content + ids), or `error`.
4. Client may use `GET .../stream?message_id=...` to reconnect.

### LLM probe

- Body: `{ "prompt": "..." }` or `{ "messages": [...] }`, optional `stream: true|false`.
- Uses same `LLMProvider` / `ModelRouter` as chat.
- Does not write to Postgres by default.
- Gated by `LLM_PROBE_ENABLED` (on in dev; configurable in prod).

### Errors

- Non-SSE: consistent JSON error shape (code, message; no secrets/stack in prod).
- SSE: `event: error` with safe client message.

## 6. LLM subsystem

### Port

```text
LLMProvider.stream_chat(messages, model, **opts) -> AsyncIterator[TokenChunk]
LLMProvider.complete_chat(messages, model, **opts) -> CompletionResult
```

### Adapters

- `OpenAICompatibleProvider` — `base_url` + `api_key` (OpenRouter, DeepSeek, etc.).
- `FakeLLMProvider` — deterministic streamed tokens for tests/CI without keys.

### ModelRouter

- Ordered model chain from env and/or `configs/llm_models.yaml`.
- On `429` / quota / payment-required / timeout → next model.
- Per-process “exhausted until TTL” map; Redis later without changing the port.
- Scenario `preferred_model: auto` uses router; explicit id pins model when available.

### Env names (values never in repo)

- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL_CHAIN` (comma-separated model ids)
- `LLM_PROBE_ENABLED`
- `DATABASE_URL`
- plus web `VITE_API_URL` for non-proxied local dev

## 7. Persistence

- PostgreSQL 16 via Docker Compose.
- SQLAlchemy 2.x + Alembic migrations.
- Repository adapters behind ports (`SessionRepository`, `MessageRepository`, `ScenarioRepository`).
- v1 Scenario implementation: filesystem YAML under `configs/scenarios/`.

## 8. Frontend (v1)

- Vite + React + TypeScript SPA.
- On load: create session, store `session_id` + `access_token`.
- Chat UI: history + input + SSE token rendering.
- Simple “Probe LLM” action calling `POST /llm/complete`.
- In Docker/prod-like: nginx serves static assets and proxies `/api` → `api:8000`.
- No heavy design system in v1; functional UI only.

## 9. Docker & local run

Compose services:

- `db` — Postgres, volume, healthcheck
- `api` — FastAPI; wait for db; run migrations on start (or dedicated migrate step)
- `web` — Vite (dev) or multi-stage nginx (prod-like)

Images:

- API: multi-stage, non-root user, `uv sync --frozen`
- Web: build → nginx

Compose references `env_file: .env` which is gitignored.

## 10. Secrets & agent safety

- Commit only `.env.example` with empty or obviously fake placeholders.
- `.gitignore` and `.cursorignore` include `.env`, `*.pem`, credential globs.
- `AGENTS.md` / Cursor rules: agents must not read, quote, or commit `.env` or secret values; discuss variable **names** only.
- Cursor Cloud / CI: inject secrets via platform secrets store as environment variables — never embed in prompts, Dockerfiles, or source.

## 11. Testing (v1)

- Unit tests for application use cases with `FakeLLMProvider`.
- API tests with real Postgres (Testcontainers or Compose `test` profile).
- At least one SSE contract test (event sequence).

## 12. Out of scope (v1)

Explicitly deferred (extension points only):

- Authentication / roles / multi-tenant orgs
- Admin UI for scenarios
- Redis-backed router state
- Voice, billing, analytics product features
- Microservices split
- Domain-specific (e.g. clinical) prompts in repo defaults

## 13. Success criteria

1. `docker compose up` brings up db + api + web; health check passes.
2. Anonymous user can open web, chat with SSE tokens, history persists in Postgres.
3. `POST /api/v1/llm/complete` returns a model response via ModelRouter.
4. Switching provider (OpenRouter ↔ DeepSeek) is config/env only.
5. No real secrets in git history; `.env` absent from agent-readable defaults.
6. Domain packages contain no product-specific medical naming.

## 14. Next step

After user approval of this spec → write implementation plan via writing-plans skill, then scaffold and implement.
