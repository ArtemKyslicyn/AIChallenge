# AIChallenge — AI Chat Platform

A domain-agnostic AI chat platform: a FastAPI hexagonal modular monolith, a Vite/React SPA, and
Postgres, wired together with Docker Compose. Answers stream over SSE, and **every assistant reply
states which model produced it** — live in the stream, in the stored row, and in the UI.

- **Design spec:** [`docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md`](docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md)
- **Implementation plan:** [`docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md`](docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md)
- **Agent conventions:** [`CLAUDE.md`](CLAUDE.md), [`AGENTS.md`](AGENTS.md)

## Run it

```bash
docker compose up --build -d
open http://localhost:8080
```

That works with **no configuration at all**: with no provider key the API falls back to
`FakeLLMProvider`, so the chat, the streaming, and the model label are all exercisable offline.

| Service | URL | Notes |
|---------|-----|-------|
| `web` | http://localhost:8080 | nginx serves the SPA and proxies `/api` |
| `api` | http://localhost:8000 | FastAPI; `/api/v1/health`, `/docs` |
| `db` | `localhost:5432` | Postgres 16, exposed for the test suite |

To use a real provider, create `.env` **in your editor** and restart:

```bash
cp .env.example .env   # then fill LLM_API_KEY and LLM_MODEL_CHAIN
docker compose up -d --build api
```

## Configuration

Names only — values live in `.env`, which is gitignored and must never be committed, printed, or
pasted into an agent chat.

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Postgres DSN (`postgresql+asyncpg://…`) |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Credentials for the `db` service |
| `LLM_BASE_URL` | OpenAI-compatible endpoint (OpenRouter, DeepSeek, …) |
| `LLM_API_KEY` | Provider key. Empty ⇒ keyless mode |
| `LLM_MODEL_CHAIN` | Comma-separated model ids, tried in order |
| `LLM_EXHAUSTED_TTL_SECONDS` | How long a rate-limited model is skipped |
| `USE_FAKE_LLM` | Force the deterministic provider |
| `LLM_PROBE_ENABLED` | Gate for `POST /api/v1/llm/complete` |
| `CORS_ALLOW_ORIGINS` | Comma-separated origins; needed only for non-proxied dev |
| `MAX_MESSAGE_CHARS` / `MAX_HISTORY_MESSAGES` | Input cap and context window cap |
| `SCENARIOS_DIR` | Override for `configs/scenarios/` |
| `VITE_API_URL` | **Build-time only.** Empty ⇒ relative `/api/v1` behind nginx |

Switching providers is configuration, not code: point `LLM_BASE_URL` and `LLM_MODEL_CHAIN` somewhere
else and restart.

## Develop without Docker

```bash
docker compose up -d db                 # Postgres only

cd apps/api
uv sync
uv run alembic upgrade head
USE_FAKE_LLM=true uv run uvicorn app.main:app --reload --port 8000

cd ../web && npm install && npm run dev  # http://localhost:5173
```

The Vite dev server proxies `/api` to `:8000`, so this needs no CORS. If you point the browser at the
API directly instead, set `CORS_ALLOW_ORIGINS=http://localhost:5173` — the API only installs CORS
middleware when that list is non-empty.

## Tests

```bash
cd apps/api
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/unit -q

docker compose up -d db
RUN_INTEGRATION=1 USE_FAKE_LLM=true \
  DATABASE_URL=postgresql+asyncpg://aichallenge:changeme@localhost:5432/aichallenge \
  uv run pytest tests/integration -q
```

No provider key is required for any of it. The integration suite migrates with Alembic and truncates
between tests. CI (`.github/workflows/ci.yml`) runs exactly this chain plus the web build.

## API

Base prefix `/api/v1`. Session-scoped routes take `X-Session-Token`.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness |
| `POST` | `/sessions` | Create an anonymous session → `{id, access_token}` |
| `GET` | `/sessions/{id}` | Metadata (never echoes the token) |
| `GET` | `/sessions/{id}/messages` | History, `model_id` per assistant row |
| `POST` | `/sessions/{id}/messages` | Send a turn; the response body is the SSE answer |
| `GET` | `/sessions/{id}/stream?message_id=` | Replay a stored answer in the same event shape |
| `POST` | `/llm/complete` | Direct probe; returns `model_id`, writes nothing |

SSE frames: `model` (as soon as a model is chosen), `token` (repeated), `message_end` (canonical
attribution), or `error`.

## Architecture

```
apps/api/src/app/
├── domain/        entities, ports, errors     — no framework imports
├── application/   use cases                   — depends on ports only
├── adapters/      api · persistence · llm · scenarios
└── core/          settings, logging, composition root
```

The layer rule is enforced by a test (`tests/unit/test_layering.py`) that parses the import graph, not
by review. Scenarios are YAML under `configs/scenarios/` behind a `ScenarioRepository` port, so moving
them into the database later does not touch the use cases.

## Known limits in v1

Deliberate, and worth knowing before you file a bug:

- **Failover only before the first token.** Once text has been streamed, a provider failure ends the
  answer with an `error` event and the partial text is saved with an `[interrupted]` marker. Switching
  models mid-answer would splice two different completions together.
- **`GET /sessions/{id}/stream` replays, it does not resume.** An answer still being generated returns
  404; live resume needs a shared buffer and is out of scope.
- **Router exhaustion state is per-process.** Fine for one container; a Redis-backed store slots in
  behind the same port.
- **No authentication.** Sessions are anonymous and hold a bearer `access_token`; `user_id` is reserved
  and unused.
- **No rate limiting** on session creation.

## Secrets

- `.env` is gitignored, excluded from both build contexts by `.dockerignore`, and never enters an image
  layer.
- Only `.env.example` — names and obviously fake placeholders — is committed.
- Agents must discuss variable **names** only, and never read, print, or commit values.
