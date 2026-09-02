# AI Chat Platform — Design Spec

**Date:** 2026-08-31 (amended 2026-09-02)  
**Status:** Implemented (v1) + post-v1 UX: model pin, compare mode, visitor history, generation prefs  
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
| LLM | OpenAI-compatible port + adapter; **RouterAI** default, also OpenRouter/DeepSeek via config |
| Model selection | Ordered `LLM_MODEL_CHAIN` with failover on quota/rate-limit, **only before the first token** |
| DB | PostgreSQL |
| Frontend | Vite + React + TypeScript SPA |
| Secrets | `.env` local + `.env.example`; Cloud/CI secrets injection |
| Backend shape | Modular monolith (not microservices in v1) |
| Scenarios | YAML files now; `ScenarioRepository` port → DB later |
| Session access | Create on visit + `access_token` in model (UI simple) |
| Architecture style | Clean/hexagonal layers |
| Model visibility | Every assistant reply shows which model produced it |

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
├── AGENTS.md                     # agent entrypoint + skill index
├── .cursor/
│   ├── rules/                    # always-on + glob rules (secrets, conventions)
│   └── skills/                   # project skills (architecture, llm, docker, …)
└── README.md
```

### Project skills (agents)

| Skill | Purpose |
|-------|---------|
| `aichallenge-architecture` | Hexagonal layers, naming, feature workflow |
| `aichallenge-secrets` | `.env` / Cloud secret safety |
| `aichallenge-llm` | Provider port, ModelRouter, `model_id`, probe |
| `aichallenge-docker` | Compose, images, run |
| `aichallenge-frontend` | SPA session, SSE, UI model label |
| `aichallenge-testing` | FakeLLM, Postgres, SSE contracts |

### Layer rules

- `domain` must not import FastAPI, SQLAlchemy, httpx, or framework code.
- `application` depends only on domain ports and entities.
- `adapters` implement ports and wire frameworks.
- Naming: `Session`, `Message`, `Scenario` — no domain leakage. (`Participant` is deferred; it is not modeled in v1.)

## 4. Domain model (v1)

### Session

- `id` (UUID)
- `access_token` (opaque secret)
- `scenario_id`
- `status` (`active` | `closed`)
- `created_at`
- `user_id` (nullable, unused in v1)
- `title` (nullable; derived from first user message for sidebar)
- `visitor_hash` (nullable; keyed by browser `X-Visitor-Id` + hashed client IP, for history grouping — never store raw IP)

### Message

- `id` (UUID)
- `session_id`
- `role` (`user` | `assistant` | `system`)
- `content`
- `model_id` (nullable string; **required for persisted assistant replies** — actual model that produced the answer after routing/failover)
- `created_at`

### Scenario (config)

- `id`
- `system_prompt` (generic)
- `preferred_model` (`auto` or model id)

## 5. HTTP API (v1)

Base prefix: `/api/v1`. Session-scoped routes require header `X-Session-Token: <access_token>`.
Visitor-scoped history requires `X-Visitor-Id` (browser UUID).

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness |
| `POST` | `/sessions` | Create session (optional `scenario_id`) → `{id, access_token}` |
| `GET` | `/sessions/history` | Summaries for sessions owned by this visitor (`title`, `message_count`) |
| `GET` | `/sessions/{id}` | Session metadata |
| `GET` | `/sessions/{id}/messages` | Message history |
| `POST` | `/sessions/{id}/messages` | User message; optional `model` pin; response is **SSE** stream of assistant tokens |
| `GET` | `/sessions/{id}/stream` | SSE **replay** of an already-persisted assistant message (same event shape, so the client reuses one parser). Not a live resume — see below. |
| `GET` | `/llm/models` | Catalog for UI selects (`id`, `label`, capability flags) |
| `POST` | `/llm/complete` | Direct LLM probe (no session persistence by default); optional generation params |

### Chat message flow

1. Client `POST /sessions/{id}/messages` with user content.
2. Server persists user message, creates pending assistant message id.
3. Response body is SSE:
   - optional `event: tool_start` / `event: tool_result` when media tools run (before or interleaved with tokens);
   - early `event: model` with `{ "model_id": "..." }` as soon as the router selects a working model (UI can show label before first token);
   - `event: token` chunks;
   - `event: message_end` with `{ message_id, content, model_id }` (canonical final attribution);
   - or `event: error`.
4. **Failover happens only before the first token.** If the router has to move down the chain before any
   token is produced, the client simply sees the `model` event for the model that ultimately answered.
   If a provider dies *after* tokens have been sent, the server persists the partial text with its
   `model_id` and ends the stream with `event: error` — it never switches models mid-answer, because
   splicing two different completions produces incoherent text.
5. If the client disconnects mid-stream, the server still persists the accumulated text and `model_id`;
   the message is then retrievable via `GET .../messages` or replayed via `GET .../stream?message_id=...`.
   v1 has **no live resume** of an in-flight stream — that needs a shared buffer and is out of scope.
6. `GET .../messages` returns `model_id` on each assistant message for history reload.

### LLM probe

- Body: `{ "prompt": "..." }` or `{ "messages": [...] }`, optional `stream: true|false`, optional `model`, `temperature`, `max_tokens`, `stop`, `reasoning`, and server-side prompt-shape flags.
- Uses same `LLMProvider` / `ModelRouter` as chat.
- Response always includes `model_id` of the model that answered (JSON field and/or SSE `model` + `message_end`).
- Does not write to Postgres by default.
- Gated by `LLM_PROBE_ENABLED` (on in dev; configurable in prod).
- The SPA **compare** mode (“Два рядом”) runs two probe calls in parallel and renders them in the thread only (not chat rows).

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

- `OpenAICompatibleProvider` — `base_url` + `api_key` (RouterAI, OpenRouter, DeepSeek, etc.).
- `FakeLLMProvider` — deterministic streamed tokens for tests/CI without keys.
- Provider switch is env-only; `ROUTERAI_KEY` is an optional alias when `LLM_API_KEY` is empty.

### ModelRouter

- Ordered model chain from env `LLM_MODEL_CHAIN` only (no YAML chain file in v1 — one source of truth).
- On `429` / quota / payment-required / timeout → next model, **only if no token has been emitted yet**.
- Per-process “exhausted until TTL” map; Redis later without changing the port.
- Scenario `preferred_model: auto` uses router; explicit id pins model when available.
- Every successful completion/stream exposes the **resolved** `model_id` to application layer for persistence and client events (never guess; use the model that actually served the response).
- The TTL clock is injectable so exhaustion/recovery is unit-testable without sleeping.

### Env names (values never in repo)

- `LLM_BASE_URL` (default production: `https://routerai.ru/api/v1`)
- `LLM_API_KEY`
- `ROUTERAI_KEY` (optional alias if `LLM_API_KEY` empty)
- `LLM_MODEL_CHAIN` (comma-separated model ids; default: quality/price balance via RouterAI catalog)
- `LLM_PROBE_ENABLED`
- `USE_FAKE_LLM`
- `DATABASE_URL`
- `CORS_ALLOW_ORIGINS` (comma-separated; required for local Vite dev against the API port)
- `MAX_MESSAGE_CHARS`, `MAX_HISTORY_MESSAGES` (input and context caps)
- `SCENARIOS_DIR` (optional override)
- `MEDIA_TOOLS_ENABLED` (default off) — chat may call free cloud media tools
- `POLLINATIONS_API_KEY` (optional; anonymous Pollinations image still works)
- `PIXAZO_API_KEY` (required for free LTX video tool)
- `MEDIA_DIR` (filesystem store for generated bytes)
- `MEDIA_IMAGE_LIMIT_PER_HOUR` / `MEDIA_VIDEO_LIMIT_PER_HOUR` (per-session in-process caps)
- plus web `VITE_API_URL` for non-proxied local dev — **build-time only**, inlined by Vite at
  `npm run build`; setting it as a runtime env var on the nginx image has no effect

### Media tools (post-v1)

Free external media (no local GPU), patterned after Kalinin SkyNet `/pollinations` + `/pixazo`:

| Tool | Provider | Notes |
|------|----------|--------|
| `generate_image` | Pollinations Flux/Sana/Turbo | Key optional; provider rate limits apply |
| `generate_video` | Pixazo LTX text-to-video | Needs `PIXAZO_API_KEY`; free LTX endpoint only |

Port: `MediaGenerator.generate_image` / `generate_video` → `MediaArtifact` (bytes, mime, extension, provider_label).
`MediaStore` persists bytes; chat embeds `/api/v1/media/{id}` in assistant markdown.
SSE: `tool_start` / `tool_result` (name, status, media_url, provider_label, error).
Agent loop: prefer OpenAI-compatible `tool_calls` via `complete_chat(..., tools=…)`; if the model returns none, fall back to a light intent detector on the user text. Max 2 tool rounds per user message. Gated by `MEDIA_TOOLS_ENABLED`.

## 7. Persistence

- PostgreSQL 16 via Docker Compose.
- SQLAlchemy 2.x + Alembic migrations.
- Repository adapters behind ports (`SessionRepository`, `MessageRepository`, `ScenarioRepository`).
- v1 Scenario implementation: filesystem YAML under `configs/scenarios/`.
- Generated media files on disk under `MEDIA_DIR` (opaque UUID filenames); not Postgres BLOBs.

## 8. Frontend (v1)

- Vite + React + TypeScript SPA.
- On load: reuse stored session if still valid on the server; otherwise create a new one
  (`session_id` + `access_token` in `localStorage` under a versioned session store bound to `visitor_id`).
  Stale ids after a DB reset must not brick chat. JSON API calls use a client timeout so a hung
  network cannot leave the boot spinner forever.
- Chat UI: thread + composer + SSE token rendering; sidebar of **this browser’s** chats only
  (merge server titles/counts for owned ids via `GET /sessions/history`).
- Composer: model select (`GET /llm/models`), mode **Один** (SSE chat, optional `model`) vs **Два рядом**
  (two probes: baseline vs template-constrained), settings for response templates / custom rules /
  temperature / reasoning. Prefs live in `localStorage`.
- Each assistant bubble shows `model_id` (subtle meta under/ beside the message); updates live on SSE `model` / `message_end`.
- In Docker/prod-like: nginx serves static assets and proxies `/api` → `api:8000` with buffering disabled
  (SSE must arrive incrementally) and a long read timeout.
- In local dev (Vite `:5173` → API `:8000`) the request is cross-origin: either use the Vite dev proxy or
  set `CORS_ALLOW_ORIGINS`. The API adds `CORSMiddleware` only when that list is non-empty.
- SSE is consumed via `fetch` + `ReadableStream` (POST bodies rule out `EventSource`); the client buffers
  across network chunks so an `event:`/`data:` pair split across two reads is not lost.
- Reloading history from the server must not depend on unstable parent callback identities — otherwise
  in-thread compare turns (not persisted) get wiped when the sidebar refreshes.
- When media tools are enabled: show tool status in the thread; render image markdown and `.mp4` media
  links as video players (no raw HTML from the model).
- No heavy design system in v1; functional UI only.

## 8.1 Production edge (host)

- Compose publishes web on loopback (`127.0.0.1:18080`); host nginx terminates TLS and proxies.
- Preferred public URL may use a dedicated HTTPS port (e.g. `:8443`) when `:443` shares the host with
  other SNI/VPN services and some client networks stall on TLS to `:443`. Document the working URL in
  the README; do not put host IPs or SSH details in public docs.
- `scripts/deploy.sh` does **not** run `docker compose down` before `up` (avoids a 502 window while
  web is stopped).

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
- Claude Code / CI: secrets via local `.env` (gitignored; never printed in chat) or CI secrets store as environment variables — never embed in prompts, Dockerfiles, or source.

## 11. Testing (v1)

- Unit tests for application use cases with `FakeLLMProvider`.
- Router tests cover: pre-first-token failover, no-failover-after-first-token, whole-chain exhaustion, and
  TTL recovery via an injected clock.
- API tests with real Postgres; schema comes from `alembic upgrade head`, never `create_all`.
- At least one SSE contract test (event sequence) plus a regression test that the assistant row ends up
  with non-empty content and a `model_id` after the stream closes.
- CI (GitHub Actions) runs ruff, mypy, unit and integration tests with `USE_FAKE_LLM=true` and
  `RUN_INTEGRATION=1`. **No provider key is required for a green build.**

## 12. Out of scope (v1)

Explicitly deferred (extension points only):

- Authentication / roles / multi-tenant orgs
- Admin UI for scenarios
- Redis-backed router state
- Live resume of an in-flight SSE stream (shared token buffer)
- Mid-answer model switching
- Rate limiting on anonymous session creation
- Voice, billing, analytics product features
- Microservices split
- Domain-specific (e.g. clinical) prompts in repo defaults

## 13. Success criteria

1. `docker compose up` brings up db + api + web; health check passes.
2. Anonymous user can open web, chat with SSE tokens, history persists in Postgres; each assistant reply shows which `model_id` answered (live and after reload).
3. `POST /api/v1/llm/complete` returns a model response via ModelRouter and includes `model_id`.
4. Switching provider (RouterAI ↔ OpenRouter ↔ DeepSeek) is config/env only.
5. No real secrets in git history; `.env` absent from agent-readable defaults **and from built image layers**
   (every build context has a `.dockerignore`).
6. Domain packages contain no product-specific medical naming.
7. `ruff`, `mypy`, unit tests and integration tests pass in CI without any provider key.

## 14. Next step

Execute `docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md` in **Claude Code** (see `CLAUDE.md`).
