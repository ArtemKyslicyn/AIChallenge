# AI Chat Platform — Implementation Plan (Cursor Cloud)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a runnable monorepo (FastAPI hexagonal API + Vite React chat + Postgres + Docker) with SSE chat, LLM probe, ModelRouter failover, and visible `model_id` on every assistant reply — safe for Cursor Cloud (no secrets in git/chat).

**Architecture:** Clean/hexagonal modular monolith under `apps/api` (`domain` → `application` → `adapters`). Vite SPA under `apps/web`. Compose runs `db` + `api` + `web`. LLM via OpenAI-compatible port + `ModelRouter` (ordered free-model chain). Domain language stays product-agnostic.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, httpx, uv, Postgres 16, Vite, React 18+, TypeScript, Docker Compose, SSE.

**Spec:** `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md`

**Skills to load before coding:** `aichallenge-architecture`, `aichallenge-secrets`, `aichallenge-llm`, `aichallenge-docker`, `aichallenge-frontend`, `aichallenge-testing` (see `AGENTS.md`).

## Global Constraints

- Never read, quote, commit, or invent real secret values; use env **names** only; Cloud injects secrets.
- No medical/role naming in code, paths, or default YAML (`patient`, `doctor`, …).
- `domain` must not import FastAPI, SQLAlchemy, or httpx.
- Assistant messages always persist and expose resolved `model_id`.
- Prefer `FakeLLMProvider` in unit/CI tests; never require a real `LLM_API_KEY` for unit tests.
- Package manager API: `uv`; frontend: `npm` inside `apps/web`.
- API mount prefix: `/api/v1`. Session header: `X-Session-Token`.
- Commit after each task with a focused message.

---

## Cursor Cloud — how to run this plan

### Before the Cloud Agent starts (human)

1. In Cursor Cloud / project **Secrets**, set (names only — paste values in the UI, never in chat):
   - `DATABASE_URL` (or rely on Compose internal URL)
   - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
   - `LLM_BASE_URL` (e.g. OpenRouter base)
   - `LLM_API_KEY`
   - `LLM_MODEL_CHAIN` (comma-separated model ids)
   - `LLM_PROBE_ENABLED=true`
2. Do **not** put secrets in the prompt or in committed files.
3. Agent may copy `.env.example` → `.env` **only if** the Cloud runner injects values into the environment and the agent writes placeholders / uses Compose env from the host — prefer Compose `environment:` from already-injected Cloud env vars over writing secrets into `.env` files in the workspace.

### Agent rules in Cloud

- Follow `AGENTS.md` and `.cursor/rules/secrets-safety.mdc`.
- If `LLM_API_KEY` is missing: implement + test with `FakeLLMProvider`; mark live LLM smoke as optional.
- Prefer `docker compose up --build` for end-to-end verification.
- Do not open or `cat` `.env` if it exists with real values.

### Definition of done (Cloud)

- [ ] `docker compose up --build -d` healthy
- [ ] `GET /api/v1/health` → 200
- [ ] Unit tests pass without real LLM key
- [ ] Chat UI loads; SSE works with Fake or real LLM
- [ ] Assistant bubbles show `model_id`
- [ ] `POST /api/v1/llm/complete` returns `model_id` when probe enabled
- [ ] No secrets in `git status` / diff

---

## File map (create during plan)

```
apps/api/pyproject.toml
apps/api/Dockerfile
apps/api/alembic.ini
apps/api/alembic/env.py
apps/api/alembic/versions/001_sessions_messages.py
apps/api/src/app/__init__.py
apps/api/src/app/main.py
apps/api/src/app/core/settings.py
apps/api/src/app/core/logging.py
apps/api/src/app/core/deps.py
apps/api/src/app/domain/entities.py
apps/api/src/app/domain/ports.py
apps/api/src/app/domain/errors.py
apps/api/src/app/application/sessions.py
apps/api/src/app/application/chat.py
apps/api/src/app/application/llm_probe.py
apps/api/src/app/adapters/persistence/db.py
apps/api/src/app/adapters/persistence/models.py
apps/api/src/app/adapters/persistence/repositories.py
apps/api/src/app/adapters/llm/fake.py
apps/api/src/app/adapters/llm/openai_compatible.py
apps/api/src/app/adapters/llm/router.py
apps/api/src/app/adapters/scenarios/yaml_repo.py
apps/api/src/app/adapters/api/health.py
apps/api/src/app/adapters/api/sessions.py
apps/api/src/app/adapters/api/llm.py
apps/api/src/app/adapters/api/schemas.py
apps/api/src/app/adapters/api/sse.py
apps/api/tests/unit/test_model_router.py
apps/api/tests/unit/test_create_session.py
apps/api/tests/unit/test_chat_stream_model_id.py
apps/api/tests/integration/conftest.py
apps/api/tests/integration/test_api_sse.py
apps/web/package.json
apps/web/vite.config.ts
apps/web/tsconfig.json
apps/web/index.html
apps/web/Dockerfile
apps/web/nginx.conf
apps/web/src/main.tsx
apps/web/src/App.tsx
apps/web/src/api/client.ts
apps/web/src/components/Chat.tsx
apps/web/src/components/Probe.tsx
configs/scenarios/default.yaml
configs/llm_models.yaml
docker-compose.yml
README.md
```

---

### Task 1: API package scaffold + health

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/app/__init__.py`
- Create: `apps/api/src/app/main.py`
- Create: `apps/api/src/app/adapters/api/health.py`
- Create: `apps/api/tests/unit/test_health.py`
- Create: `README.md` (Cloud-oriented run notes; no secrets)

**Interfaces:**
- Produces: FastAPI app factory `create_app()` exposing `GET /api/v1/health` → `{"status":"ok"}`

- [ ] **Step 1: Write failing health test**

```python
# apps/api/tests/unit/test_health.py
from fastapi.testclient import TestClient
from app.main import create_app

def test_health_ok():
    client = TestClient(create_app())
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Run test — expect fail (module missing)**

```bash
cd apps/api && uv sync && uv run pytest tests/unit/test_health.py -v
```

Expected: FAIL import or 404

- [ ] **Step 3: Minimal `pyproject.toml` + app**

`pyproject.toml` essentials:

```toml
[project]
name = "aichallenge-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.30",
  "alembic>=1.14",
  "httpx>=0.28",
  "pydantic-settings>=2.6",
  "pyyaml>=6.0",
]

[dependency-groups]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "anyio>=4.6"]

[tool.uv]
package = true

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/app"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["src"]
```

```python
# apps/api/src/app/adapters/api/health.py
from fastapi import APIRouter
router = APIRouter(tags=["health"])

@router.get("/health")
async def health():
    return {"status": "ok"}
```

```python
# apps/api/src/app/main.py
from fastapi import FastAPI
from app.adapters.api.health import router as health_router

def create_app() -> FastAPI:
    app = FastAPI(title="AIChallenge API")
    app.include_router(health_router, prefix="/api/v1")
    return app

app = create_app()
```

- [ ] **Step 4: Re-run test — PASS**

```bash
cd apps/api && uv run pytest tests/unit/test_health.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/api README.md
git commit -m "feat(api): scaffold FastAPI app with health endpoint"
```

---

### Task 2: Domain entities + ports

**Files:**
- Create: `apps/api/src/app/domain/entities.py`
- Create: `apps/api/src/app/domain/ports.py`
- Create: `apps/api/src/app/domain/errors.py`
- Create: `apps/api/tests/unit/test_entities.py`

**Interfaces:**
- Produces:

```python
# entities (dataclasses / attrs — pure)
class SessionStatus(str, Enum):
    ACTIVE = "active"
    CLOSED = "closed"

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

@dataclass(slots=True)
class Session:
    id: UUID
    access_token: str
    scenario_id: str
    status: SessionStatus
    created_at: datetime
    user_id: UUID | None = None

@dataclass(slots=True)
class Message:
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    created_at: datetime
    model_id: str | None = None

@dataclass(slots=True)
class Scenario:
    id: str
    system_prompt: str
    preferred_model: str  # "auto" or model id

@dataclass(slots=True)
class ChatMessage:
    role: MessageRole
    content: str

@dataclass(slots=True)
class TokenChunk:
    text: str
    model_id: str

@dataclass(slots=True)
class CompletionResult:
    content: str
    model_id: str
```

```python
# ports.py — Protocol classes
class SessionRepository(Protocol):
    async def create(self, session: Session) -> Session: ...
    async def get(self, session_id: UUID) -> Session | None: ...

class MessageRepository(Protocol):
    async def add(self, message: Message) -> Message: ...
    async def list_for_session(self, session_id: UUID) -> list[Message]: ...
    async def update_content(self, message_id: UUID, content: str, model_id: str | None) -> Message: ...
    async def get(self, message_id: UUID) -> Message | None: ...

class ScenarioRepository(Protocol):
    async def get(self, scenario_id: str) -> Scenario | None: ...
    async def get_default(self) -> Scenario: ...

class LLMProvider(Protocol):
    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[TokenChunk]: ...
    async def complete_chat(self, messages: list[ChatMessage], model: str) -> CompletionResult: ...
```

- [ ] **Step 1: Write a small entity construction test** asserting `Message.model_id` can be set for assistant roles.

- [ ] **Step 2: Run — fail / then implement entities+ports — pass**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): add domain entities and ports"
```

---

### Task 3: FakeLLMProvider + ModelRouter (TDD)

**Files:**
- Create: `apps/api/src/app/adapters/llm/fake.py`
- Create: `apps/api/src/app/adapters/llm/router.py`
- Create: `apps/api/src/app/domain/errors.py` (add `LLMExhaustedError`, `LLMProviderError`)
- Create: `apps/api/tests/unit/test_model_router.py`
- Create: `configs/llm_models.yaml`

**Interfaces:**
- Consumes: `LLMProvider`, `TokenChunk`, `CompletionResult`, `ChatMessage`
- Produces:

```python
class ModelRouter:
    def __init__(self, provider: LLMProvider, model_chain: list[str], exhausted_ttl_seconds: int = 300): ...
    async def stream_chat(self, messages: list[ChatMessage], preferred_model: str = "auto") -> AsyncIterator[TokenChunk]: ...
    async def complete_chat(self, messages: list[ChatMessage], preferred_model: str = "auto") -> CompletionResult: ...
```

Failover: on provider raising an error with status in `{429, 402}` or named `quota`/`timeout`, mark model exhausted until TTL, try next. Every yielded `TokenChunk.model_id` / `CompletionResult.model_id` is the model that succeeded.

- [ ] **Step 1: Failing tests**

```python
# apps/api/tests/unit/test_model_router.py
import pytest
from app.adapters.llm.fake import FakeLLMProvider, FlakyLLMProvider
from app.adapters.llm.router import ModelRouter
from app.domain.entities import ChatMessage, MessageRole

@pytest.mark.asyncio
async def test_router_failsover_and_reports_second_model():
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    result = await router.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="x")], preferred_model="auto"
    )
    assert result.model_id == "model-b"
    assert result.content == "hi"

@pytest.mark.asyncio
async def test_fake_stream_emits_model_id():
    provider = FakeLLMProvider(text="ab", model_id="fake-1")
    chunks = [c async for c in provider.stream_chat([], model="fake-1")]
    assert "".join(c.text for c in chunks) == "ab"
    assert all(c.model_id == "fake-1" for c in chunks)
```

Implement `FlakyLLMProvider` in `fake.py` for tests (or same module).

- [ ] **Step 2: Run — FAIL**

- [ ] **Step 3: Implement Fake + Router minimally**

- [ ] **Step 4: Run — PASS**

- [ ] **Step 5: Add `configs/llm_models.yaml`**

```yaml
# Default chain used when LLM_MODEL_CHAIN env is empty
models:
  - id: openrouter/free-placeholder-a
  - id: openrouter/free-placeholder-b
```

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(api): add FakeLLM and ModelRouter with failover"
```

---

### Task 4: Settings + OpenAI-compatible provider (no secrets in files)

**Files:**
- Create: `apps/api/src/app/core/settings.py`
- Create: `apps/api/src/app/adapters/llm/openai_compatible.py`
- Create: `apps/api/tests/unit/test_settings.py`
- Modify: `.env.example` if missing any names (values empty)

**Interfaces:**
- Produces:

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://aichallenge:changeme@localhost:5432/aichallenge"
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    llm_model_chain: str = ""  # csv
    llm_probe_enabled: bool = True
    scenarios_dir: str = ""  # default resolved relative to repo configs/
    use_fake_llm: bool = False  # True in tests / when no key

    def model_chain_list(self) -> list[str]: ...
```

`OpenAICompatibleProvider` uses httpx AsyncClient; `Authorization: Bearer {key}`; POST `{base}/chat/completions` with `stream: true|false`. Map chunks to `TokenChunk(text=delta, model_id=model)`.

- [ ] **Step 1: Test settings parse `LLM_MODEL_CHAIN` csv**

- [ ] **Step 2: Implement settings + provider**

- [ ] **Step 3: Do not write real keys into any file**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(api): add settings and OpenAI-compatible LLM client"
```

---

### Task 5: Postgres models, repos, Alembic

**Files:**
- Create: `apps/api/src/app/adapters/persistence/db.py`
- Create: `apps/api/src/app/adapters/persistence/models.py`
- Create: `apps/api/src/app/adapters/persistence/repositories.py`
- Create: `apps/api/alembic.ini`
- Create: `apps/api/alembic/env.py`
- Create: `apps/api/alembic/versions/001_sessions_messages.py`

**Interfaces:**
- Tables: `sessions` (`id`, `access_token`, `scenario_id`, `status`, `created_at`, `user_id` nullable), `messages` (`id`, `session_id` FK, `role`, `content`, `model_id` nullable, `created_at`)
- Produces: `SqlAlchemySessionRepository`, `SqlAlchemyMessageRepository` implementing ports
- `create_engine` / `async_sessionmaker` from `Settings.database_url`

- [ ] **Step 1: Write migration for both tables including `messages.model_id`**

- [ ] **Step 2: Implement ORM models + repos mapping to domain entities**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): add Postgres models, repos, and initial Alembic migration"
```

---

### Task 6: YAML ScenarioRepository + default scenario

**Files:**
- Create: `apps/api/src/app/adapters/scenarios/yaml_repo.py`
- Create: `configs/scenarios/default.yaml`
- Create: `apps/api/tests/unit/test_yaml_scenarios.py`

**Interfaces:**
- `YamlScenarioRepository(scenarios_dir: Path)` implements `ScenarioRepository`
- Default file:

```yaml
id: default
system_prompt: >
  You are a helpful assistant conducting a structured intake conversation.
  Ask clear questions one at a time. Stay neutral and professional.
preferred_model: auto
```

(No medical role nouns.)

- [ ] **Step 1: Test loads default scenario**

- [ ] **Step 2: Implement — PASS**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): add YAML scenario repository and default scenario"
```

---

### Task 7: Application use cases — sessions + probe

**Files:**
- Create: `apps/api/src/app/application/sessions.py`
- Create: `apps/api/src/app/application/llm_probe.py`
- Create: `apps/api/tests/unit/test_create_session.py`
- Create: `apps/api/tests/unit/test_llm_probe.py`

**Interfaces:**
- Produces:

```python
async def create_session(
    *,
    sessions: SessionRepository,
    scenarios: ScenarioRepository,
    scenario_id: str | None,
    token_factory: Callable[[], str],
    id_factory: Callable[[], UUID],
    now: Callable[[], datetime],
) -> Session: ...

async def complete_probe(
    *,
    router: ModelRouter,
    messages: list[ChatMessage],
    preferred_model: str = "auto",
    enabled: bool,
) -> CompletionResult: ...
```

`complete_probe` raises domain error if `enabled` is False.

- [ ] **Step 1: Unit tests with in-memory fakes for repos + FakeLLM**

- [ ] **Step 2: Implement use cases**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): add create_session and llm probe use cases"
```

---

### Task 8: Chat use case with SSE event sequence (model_id)

**Files:**
- Create: `apps/api/src/app/application/chat.py`
- Create: `apps/api/src/app/adapters/api/sse.py`
- Create: `apps/api/tests/unit/test_chat_stream_model_id.py`

**Interfaces:**
- Produces async generator of typed events:

```python
@dataclass
class ModelEvent:
    model_id: str

@dataclass
class TokenEvent:
    text: str

@dataclass
class MessageEndEvent:
    message_id: UUID
    content: str
    model_id: str

@dataclass
class ErrorEvent:
    message: str

async def send_user_message_and_stream(
    *,
    session_id: UUID,
    access_token: str,
    content: str,
    sessions: SessionRepository,
    messages: MessageRepository,
    scenarios: ScenarioRepository,
    router: ModelRouter,
    id_factory: Callable[[], UUID],
    now: Callable[[], datetime],
) -> AsyncIterator[ModelEvent | TokenEvent | MessageEndEvent | ErrorEvent]:
    ...
```

Behavior:
1. AuthZ: session exists and `access_token` matches; else error event / raise unauthorized.
2. Persist user `Message`.
3. Create assistant `Message` with empty content, `model_id=None`.
4. Load scenario; build chat history including system prompt.
5. As router streams: first chunk emits `ModelEvent`; on `model_id` change emit another `ModelEvent`; yield `TokenEvent`s; accumulate text.
6. `update_content` assistant message with final text + `model_id`; yield `MessageEndEvent`.

SSE helper maps events to:

```
event: model
data: {"model_id":"..."}

event: token
data: {"text":"..."}

event: message_end
data: {"message_id":"...","content":"...","model_id":"..."}

event: error
data: {"message":"..."}
```

- [ ] **Step 1: Unit test with FakeLLM asserts event order and final `model_id`**

- [ ] **Step 2: Implement — PASS**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(api): add chat streaming use case with model attribution"
```

---

### Task 9: FastAPI routers — sessions, messages, stream, probe + DI

**Files:**
- Create: `apps/api/src/app/core/deps.py`
- Create: `apps/api/src/app/adapters/api/schemas.py`
- Create: `apps/api/src/app/adapters/api/sessions.py`
- Create: `apps/api/src/app/adapters/api/llm.py`
- Modify: `apps/api/src/app/main.py`

**Interfaces:**
- `POST /api/v1/sessions` → `{id, access_token}`
- `GET /api/v1/sessions/{id}` header `X-Session-Token`
- `GET /api/v1/sessions/{id}/messages` → list including `model_id`
- `POST /api/v1/sessions/{id}/messages` body `{content}` → `StreamingResponse` text/event-stream
- `GET /api/v1/sessions/{id}/stream?message_id=` → SSE reconnect (v1: re-read completed message or error if unknown)
- `POST /api/v1/llm/complete` body `{prompt?|messages?, stream?}` → JSON or SSE; includes `model_id`; 404/403 if probe disabled

DI: if `settings.use_fake_llm` or empty `llm_api_key` → `FakeLLMProvider`; else OpenAI-compatible + ModelRouter from `model_chain_list()` or YAML.

- [ ] **Step 1: Wire routers; keep health**

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(api): expose sessions, SSE chat, and LLM probe HTTP API"
```

---

### Task 10: Docker Compose — db + api

**Files:**
- Create: `apps/api/Dockerfile`
- Create: `docker-compose.yml`
- Modify: `.env.example` (ensure Compose var names match)

**Dockerfile (api) sketch:**
- multi-stage, `uv sync --frozen` (generate lock in task: `uv lock`)
- non-root user
- CMD: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
- `PYTHONPATH=/app/src` or install package

**Compose:**
- `db`: `postgres:16`, healthcheck `pg_isready`, volume
- `api`: build `apps/api`, `depends_on: db: condition: service_healthy`, `env_file: .env` optional, map env from Cloud
- ports: `8000:8000` for Cloud smoke

- [ ] **Step 1: `uv lock` in `apps/api`**

- [ ] **Step 2: Write Dockerfile + compose**

- [ ] **Step 3: Build & health (Cloud)**

```bash
docker compose up --build -d db api
curl -sf http://localhost:8000/api/v1/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Commit**

```bash
git commit -m "chore: add API Dockerfile and Compose for db+api"
```

---

### Task 11: Integration SSE test (Postgres)

**Files:**
- Create: `apps/api/tests/integration/conftest.py`
- Create: `apps/api/tests/integration/test_api_sse.py`

**Approach:** Use Compose Postgres URL from env `DATABASE_URL` (Cloud) or skip if unavailable:

```python
pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")
```

Test:
1. Create session
2. POST message with Fake LLM forced via `USE_FAKE_LLM=true`
3. Parse SSE: expect `model` then `token`+ then `message_end` with same `model_id`
4. GET messages → assistant has `model_id`

- [ ] **Step 1: Implement + run with `RUN_INTEGRATION=1 USE_FAKE_LLM=true`**

- [ ] **Step 2: Commit**

```bash
git commit -m "test(api): add SSE integration test against Postgres"
```

---

### Task 12: Web SPA — session, chat SSE, model label, probe

**Files:**
- Create: full Vite React TS app under `apps/web/`
- Create: `apps/web/src/api/client.ts`
- Create: `apps/web/src/components/Chat.tsx`
- Create: `apps/web/src/components/Probe.tsx`
- Create: `apps/web/src/App.tsx`

**Interfaces:**
- `createSession()`, `listMessages(sessionId, token)`, `sendMessageSSE(sessionId, token, content, onEvent)`, `probeComplete(prompt)`
- Base URL: `import.meta.env.VITE_API_URL || "/api/v1"`
- UI: messages list; assistant meta line showing `model_id`; input; Probe panel

SSE client: read stream from `POST .../messages`, parse `event:` / `data:` lines.

- [ ] **Step 1: Scaffold Vite React-TS**

```bash
cd apps/web && npm create vite@latest . -- --template react-ts
npm install
```

- [ ] **Step 2: Implement Chat + Probe**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat(web): add chat SPA with SSE and model_id labels"
```

---

### Task 13: Web Docker + nginx proxy + full Compose

**Files:**
- Create: `apps/web/Dockerfile`
- Create: `apps/web/nginx.conf`
- Modify: `docker-compose.yml` add `web`

**nginx.conf:**
- serve `/usr/share/nginx/html`
- `location /api/ { proxy_pass http://api:8000/api/; proxy_buffering off; proxy_http_version 1.1; }` (SSE-friendly)

- [ ] **Step 1: Multi-stage web image**

- [ ] **Step 2: `docker compose up --build -d`**

- [ ] **Step 3: Manual smoke — open web, send message (Fake or real), confirm model label**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(web): Docker/nginx proxy and wire full Compose stack"
```

---

### Task 14: README + Cloud checklist + status polish

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md` status → `Implemented (v1 plan executed)` only if done; otherwise leave and point to this plan
- Ensure `.gitignore` / `.cursorignore` / `.env.example` complete

**README must include:**
- Architecture one-liner + link to spec + this plan
- `docker compose up --build`
- Cloud Secrets table (names only)
- `USE_FAKE_LLM=true` for keyless demo
- Explicit: never commit `.env`

- [ ] **Step 1: Write README**

- [ ] **Step 2: Final verification checklist (Cloud)**

```bash
docker compose ps
curl -sf http://localhost:8000/api/v1/health
cd apps/api && uv run pytest tests/unit -v
# optional: RUN_INTEGRATION=1 USE_FAKE_LLM=true uv run pytest tests/integration -v
```

- [ ] **Step 3: Confirm `git status` has no `.env`**

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: add Cloud-oriented README and run checklist"
```

---

## Spec coverage self-check

| Spec item | Task(s) |
|-----------|---------|
| Hexagonal layout / SOLID | 1–9 |
| Anonymous session + token | 7, 9, 12 |
| SSE tokens + model events | 8, 9, 11, 12 |
| `model_id` persistence + UI | 5, 8, 9, 12 |
| OpenAI-compatible + Fake + Router | 3, 4 |
| `/llm/complete` probe | 7, 9, 12 |
| YAML scenarios + port | 6 |
| Postgres + Alembic | 5, 10 |
| Docker Compose api/web/db | 10, 13 |
| Secrets / Cloud / no .env in git | Global + 4, 14 |
| Domain-agnostic naming | Global + 6 |
| Unit + SSE integration tests | 3, 7, 8, 11 |

## Out of scope (do not implement in this plan)

Auth, admin scenario UI, Redis router state, voice, billing, microservices, clinical default prompts.

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-31-ai-chat-platform-cloud.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

**Which approach?** For Cursor Cloud: open a Cloud Agent with this file as the brief, inject Secrets first, and instruct: *“Execute `docs/superpowers/plans/2026-08-31-ai-chat-platform-cloud.md` task-by-task; follow AGENTS.md; never read or print `.env`.”*
