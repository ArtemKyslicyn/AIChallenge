# AI Chat Platform — Implementation Plan (Claude Code)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Target runner:** [Claude Code](https://claude.ai/code) (separate Anthropic account — not Cursor Cloud). Follow `CLAUDE.md` + `AGENTS.md`.

**Goal:** Ship a runnable monorepo (FastAPI hexagonal API + Vite React chat + Postgres + Docker) with SSE chat, LLM probe, ModelRouter failover, and visible `model_id` on every assistant reply — safe for Claude Code (no secrets in git/chat).

**Architecture:** Clean/hexagonal modular monolith under `apps/api` (`domain` → `application` → `adapters`). Vite SPA under `apps/web`. Compose runs `db` + `api` + `web`. LLM via OpenAI-compatible port + `ModelRouter` (ordered free-model chain). Domain language stays product-agnostic.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy 2, Alembic, httpx, uv, Postgres 16, Vite, React 18+, TypeScript, Docker Compose, SSE.

**Spec:** `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md`

**Skills to load before coding:** `aichallenge-architecture`, `aichallenge-secrets`, `aichallenge-llm`, `aichallenge-docker`, `aichallenge-frontend`, `aichallenge-testing` (see `AGENTS.md`).

## Global Constraints

- Never read, quote, commit, or invent real secret values; use env **names** only; values live in local `.env` (gitignored) or the shell env of the Claude Code session.
- No medical/role naming in code, paths, or default YAML (`patient`, `doctor`, …).
- `domain` must not import FastAPI, SQLAlchemy, or httpx.
- Assistant messages always persist and expose resolved `model_id`.
- Prefer `FakeLLMProvider` in unit/CI tests; never require a real `LLM_API_KEY` for unit tests.
- Package manager API: `uv`; frontend: `npm` inside `apps/web`.
- API mount prefix: `/api/v1`. Session header: `X-Session-Token`.
- **Failover is allowed only before the first token is emitted.** Once any token of an assistant reply has been streamed, a provider failure ends the stream with `event: error` — never switch models mid-answer (would splice two different replies).
- **Model chain comes from `LLM_MODEL_CHAIN` env only.** No YAML chain file in v1.
- Input limits are enforced in the application layer: `MAX_MESSAGE_CHARS` for a single user message, `MAX_HISTORY_MESSAGES` for the history slice sent to the LLM.
- Every `docker build` context must be covered by a `.dockerignore` that excludes `.env`, `.venv/`, `node_modules/` — a secret must never end up in an image layer.
- Lint/type-check clean: `ruff check`, `ruff format --check`, `mypy src`.
- Commit after each task with a focused message.

---

## Claude Code — how to run this plan

### Before starting (human, on the Claude Code machine)

1. Copy env template locally (do this yourself; do **not** paste values into the Claude Code chat):
   ```bash
   cp .env.example .env
   # edit .env in your editor — fill LLM_API_KEY, POSTGRES_*, etc.
   ```
2. Required names in `.env` (values never in chat/commits):
   - `DATABASE_URL` (or Compose-internal URL for `db` service)
   - `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`
   - `LLM_BASE_URL` (e.g. OpenRouter)
   - `LLM_API_KEY`
   - `LLM_MODEL_CHAIN` (comma-separated model ids)
   - `LLM_PROBE_ENABLED=true`
   - `USE_FAKE_LLM` (`true` for the keyless path)
   - `CORS_ALLOW_ORIGINS` (comma-separated; needed for non-Docker dev where Vite runs on `:5173`)
   - `SCENARIOS_DIR` (optional; defaults to repo `configs/scenarios/`)
3. Optional keyless path: set `USE_FAKE_LLM=true` and leave `LLM_API_KEY` empty — agent must still implement real provider + router.
4. Open Claude Code in this repo (Anthropic account). Point it at this plan file.

### Agent rules (Claude Code)

- Follow `CLAUDE.md`, `AGENTS.md`, and project skills under `.cursor/skills/` (same conventions).
- **Never** `cat`/open/quote `.env` or print secret values in the transcript.
- If `LLM_API_KEY` is missing: implement + unit-test with `FakeLLMProvider`; live LLM smoke optional.
- Prefer `docker compose up --build` for end-to-end verification.
- Commit after each task; do not force-push; do not amend unless the human asks.

### Starter prompt (paste into Claude Code)

```text
Execute docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md task-by-task.
Follow CLAUDE.md and AGENTS.md.
Never read, print, or commit .env or secret values.
Use FakeLLM when LLM_API_KEY is unset.
Mark checkboxes as you complete steps; commit after each task.
```

### Definition of done (Claude Code)

- [ ] `docker compose up --build -d` healthy
- [ ] `GET /api/v1/health` → 200
- [ ] Unit tests pass without real LLM key
- [ ] Chat UI loads; SSE works with Fake or real LLM
- [ ] Assistant bubbles show `model_id`
- [ ] `POST /api/v1/llm/complete` returns `model_id` when probe enabled
- [ ] `ruff check`, `ruff format --check`, `mypy src` clean
- [ ] Integration tests pass: `RUN_INTEGRATION=1 USE_FAKE_LLM=true uv run pytest tests/integration`
- [ ] CI workflow green on push
- [ ] No secrets in `git status` / diff; `.env` not present in any built image (see the check in Task 10 Step 4)

---

## File map (create during plan)

```
apps/api/pyproject.toml
apps/api/Dockerfile
apps/api/.dockerignore
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
apps/api/tests/unit/test_health.py
apps/api/tests/unit/test_entities.py
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
apps/web/.dockerignore
apps/web/nginx.conf
apps/web/src/main.tsx
apps/web/src/App.tsx
apps/web/src/api/client.ts
apps/web/src/components/Chat.tsx
apps/web/src/components/Probe.tsx
configs/scenarios/default.yaml
docker-compose.yml
.github/workflows/ci.yml
README.md
```

---

### Task 1: API package scaffold + health

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/src/app/__init__.py`
- Create: `apps/api/src/app/main.py`
- Create: `apps/api/src/app/core/logging.py`
- Create: `apps/api/src/app/adapters/api/health.py`
- Create: `apps/api/tests/unit/test_health.py`
- Create: `README.md` (Claude Code–oriented run notes; no secrets)

**Interfaces:**
- Produces: FastAPI app factory `create_app()` exposing `GET /api/v1/health` → `{"status":"ok"}`

- [x] **Step 1: Write failing health test**

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

- [x] **Step 2: Run test — expect fail (module missing)**

```bash
cd apps/api && uv sync && uv run pytest tests/unit/test_health.py -v
```

Expected: FAIL import or 404

- [x] **Step 3: Minimal `pyproject.toml` + app**

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
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "anyio>=4.6", "ruff>=0.8", "mypy>=1.13"]

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

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]

[tool.mypy]
python_version = "3.12"
strict = true
mypy_path = "src"
```

`core/logging.py`: a single `configure_logging(level: str = "INFO") -> None` using stdlib `logging` with a
JSON-ish or key=value formatter. Call it once from `create_app()`. **Never log message content, headers, or
`access_token` values** — log `session_id`, `message_id`, `model_id`, and durations only.

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
from app.core.logging import configure_logging

def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="AIChallenge API")
    app.include_router(health_router, prefix="/api/v1")
    return app

app = create_app()
```

CORS middleware is added in Task 9 (needs `Settings`, which does not exist yet).

- [x] **Step 4: Re-run test — PASS**

```bash
cd apps/api && uv run pytest tests/unit/test_health.py -v
uv run ruff check . && uv run ruff format --check .
```

- [x] **Step 5: Commit**

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

- [x] **Step 1: Write a small entity construction test** asserting `Message.model_id` can be set for assistant roles.

- [x] **Step 2: Run — fail / then implement entities+ports — pass**

- [x] **Step 3: Commit**

```bash
git commit -m "feat(api): add domain entities and ports"
```

---

### Task 3: FakeLLMProvider + ModelRouter (TDD)

**Files:**
- Create: `apps/api/src/app/adapters/llm/fake.py`
- Create: `apps/api/src/app/adapters/llm/router.py`
- Modify: `apps/api/src/app/domain/errors.py` (add `LLMExhaustedError`, `LLMProviderError`, `LLMStreamAbortedError`)
- Create: `apps/api/tests/unit/test_model_router.py`

**Interfaces:**
- Consumes: `LLMProvider`, `TokenChunk`, `CompletionResult`, `ChatMessage`
- Produces:

```python
class ModelRouter:
    def __init__(
        self,
        provider: LLMProvider,
        model_chain: list[str],
        exhausted_ttl_seconds: int = 300,
        now: Callable[[], float] = time.monotonic,   # injectable clock — TTL must be testable
    ): ...
    async def stream_chat(self, messages: list[ChatMessage], preferred_model: str = "auto") -> AsyncIterator[TokenChunk]: ...
    async def complete_chat(self, messages: list[ChatMessage], preferred_model: str = "auto") -> CompletionResult: ...
```

**Failover rules (locked):**

1. On a provider error with status in `{429, 402, 408}` or named `quota` / `rate_limit` / `timeout`: mark the model exhausted until `now() + exhausted_ttl_seconds` and try the next model in the chain.
2. **`stream_chat` may only fail over before it has yielded its first `TokenChunk`.** Once a token has left the router, a provider failure raises `LLMStreamAbortedError` carrying the partial text and the `model_id` — the caller ends the stream with an error event. Switching models mid-answer would splice two different replies.
3. When the whole chain is exhausted: raise `LLMExhaustedError`.
4. `preferred_model != "auto"` pins that model; if it is exhausted or missing from the chain, fall back to normal chain order (still respecting rule 2).
5. Every yielded `TokenChunk.model_id` / `CompletionResult.model_id` is the model that actually served the response — never a guess.

The chain is built from `Settings.model_chain_list()` (env `LLM_MODEL_CHAIN`). There is no YAML chain file in v1.

- [x] **Step 1: Failing tests**

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

@pytest.mark.asyncio
async def test_stream_failsover_before_first_token():
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    chunks = [c async for c in router.stream_chat([], preferred_model="auto")]
    assert "".join(c.text for c in chunks) == "hi"
    assert {c.model_id for c in chunks} == {"model-b"}

@pytest.mark.asyncio
async def test_stream_does_not_failover_after_first_token():
    # model-a yields "he", then dies with 429 — router must NOT continue on model-b
    provider = FlakyLLMProvider(fail_mid_stream={"model-a"}, partial_text="he", ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"])
    seen = []
    with pytest.raises(LLMStreamAbortedError) as exc:
        async for c in router.stream_chat([], preferred_model="auto"):
            seen.append(c)
    assert "".join(c.text for c in seen) == "he"
    assert exc.value.model_id == "model-a"

@pytest.mark.asyncio
async def test_exhausted_model_recovers_after_ttl():
    clock = {"t": 0.0}
    provider = FlakyLLMProvider(fail_models={"model-a"}, fail_status=429, ok_text="hi")
    router = ModelRouter(provider, ["model-a", "model-b"], exhausted_ttl_seconds=300,
                         now=lambda: clock["t"])
    await router.complete_chat([], preferred_model="auto")
    provider.fail_models.clear()
    clock["t"] = 301.0
    assert (await router.complete_chat([], preferred_model="auto")).model_id == "model-a"
```

Implement `FlakyLLMProvider` in `fake.py` for tests (or same module): it must support failing *before*
the first chunk (`fail_models`) and failing *mid-stream* after `partial_text` (`fail_mid_stream`).

- [x] **Step 2: Run — FAIL**

- [x] **Step 3: Implement Fake + Router minimally**

- [x] **Step 4: Run — PASS**

- [x] **Step 5: Commit**

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
    cors_allow_origins: str = ""  # csv; e.g. "http://localhost:5173"
    max_message_chars: int = 8000        # reject longer user messages with 422
    max_history_messages: int = 40       # newest N messages sent to the LLM (system prompt always kept)
    exhausted_ttl_seconds: int = 300
    log_level: str = "INFO"

    def model_chain_list(self) -> list[str]: ...
    def cors_origins_list(self) -> list[str]: ...
```

`OpenAICompatibleProvider` uses httpx AsyncClient; `Authorization: Bearer {key}`; POST `{base}/chat/completions` with `stream: true|false`. Map chunks to `TokenChunk(text=delta, model_id=model)`.

- [x] **Step 1: Test settings parse `LLM_MODEL_CHAIN` and `CORS_ALLOW_ORIGINS` csv** (empty string → empty list; whitespace trimmed; no crash when unset)

- [x] **Step 2: Implement settings + provider**

- [x] **Step 3: Do not write real keys into any file**

- [x] **Step 4: Commit**

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
- Alembic is the **single source of schema truth** — never `Base.metadata.create_all()` in app or test code; the integration suite (Task 11) runs `alembic upgrade head`.
- `alembic/env.py` must use the async engine (`connectable.connect()` inside `asyncio.run` / `run_sync`) because `DATABASE_URL` uses the `postgresql+asyncpg` driver.
- `sessions.access_token` gets a unique index; `messages` gets an index on `(session_id, created_at)` for history reads.

- [x] **Step 1: Write migration for both tables including `messages.model_id`**

- [x] **Step 2: Implement ORM models + repos mapping to domain entities**

- [x] **Step 3: Commit**

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

- [x] **Step 1: Test loads default scenario**

- [x] **Step 2: Implement — PASS**

- [x] **Step 3: Commit**

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

**Token handling (locked):**
- `token_factory` default is `secrets.token_urlsafe(32)` — never `uuid4()`, never `random`.
- Session authZ compares tokens with `secrets.compare_digest`, never `==`.
- `access_token` is returned by `POST /sessions` and never logged, never included in any other response body, and never echoed in error messages.
- `id_factory` / `now` stay injectable so use-case tests are deterministic.

- [x] **Step 1: Unit tests with in-memory fakes for repos + FakeLLM**

- [x] **Step 2: Implement use cases**

- [x] **Step 3: Commit**

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
    max_message_chars: int,
    max_history_messages: int,
) -> AsyncIterator[ModelEvent | TokenEvent | MessageEndEvent | ErrorEvent]:
    ...
```

Behavior:
1. AuthZ: session exists, status is `active`, and `access_token` matches via `compare_digest`; else raise unauthorized (the router layer turns it into 401/403 *before* the stream starts — do not return 200 + an error event for an auth failure).
2. Validate `len(content) <= max_message_chars` and `content.strip()` non-empty; else raise a validation error (422 before the stream starts).
3. Persist user `Message`.
4. Create assistant `Message` with empty content, `model_id=None`.
5. Load scenario; build the LLM history as `[system_prompt] + last max_history_messages messages` (newest-last). The full history stays in Postgres — only the slice sent to the provider is capped.
6. As router streams: the first chunk emits `ModelEvent`, then `TokenEvent`s; accumulate text. Because failover is pre-first-token only (Task 3), **at most one `ModelEvent` per reply** in the happy path.
7. `update_content` assistant message with final text + `model_id`; yield `MessageEndEvent`.

**Failure and disconnect handling (must be implemented, not left to chance):**

- `LLMStreamAbortedError` (provider died mid-answer): persist the partial text with the resolved `model_id` and append a marker so the reply is never silently truncated-looking, then yield `ErrorEvent`. Never fail over to another model here.
- `LLMExhaustedError` (whole chain down): persist nothing further, delete or mark the empty assistant message, yield `ErrorEvent` with a safe client message (no provider text, no key, no URL).
- **Client disconnect:** wrap the streaming loop in `try/finally`. On `GeneratorExit` / `asyncio.CancelledError`, still persist whatever text was accumulated with its `model_id` before re-raising. Without this an interrupted stream leaves an assistant row with empty content and `model_id=None` forever, which then reloads as a blank bubble.
- The unit test must cover all three paths (normal end, mid-stream abort, cancellation) with `FakeLLMProvider` / `FlakyLLMProvider`.

**Ownership of the DB session:** this generator must receive repositories bound to a DB session whose
lifetime it controls (opened inside the generator, closed in its `finally`). It must **not** rely on a
request-scoped `Depends(get_db)` session — FastAPI closes those before a `StreamingResponse` body finishes,
so step 7's `update_content` would run on a closed session. See Task 9.

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

- [x] **Step 1: Unit test with FakeLLM asserts event order and final `model_id`** (`model` → `token`+ → `message_end`, all three carrying the same `model_id`)

- [x] **Step 2: Unit tests for mid-stream abort, exhausted chain, cancellation, oversized message, history truncation**

- [x] **Step 3: Implement — PASS**

- [x] **Step 4: Commit**

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
- `GET /api/v1/sessions/{id}/stream?message_id=` → **replay of an already-persisted assistant message**, emitted as the same `model` / `token` / `message_end` sequence so the client can reuse one parser. Returns 404 while the message is still being generated. This is *not* a live resume of an in-flight stream (see spec §5) — there is no shared buffer in v1.
- `POST /api/v1/llm/complete` body `{prompt?|messages?, stream?}` → JSON or SSE; includes `model_id`; 404/403 if probe disabled

**DI:** if `settings.use_fake_llm` or empty `llm_api_key` → `FakeLLMProvider`; else `OpenAICompatibleProvider`.
`ModelRouter` is built from `settings.model_chain_list()`; if that list is empty and `use_fake_llm` is set,
fall back to a single fake model id. Empty chain + real provider → fail fast at startup with a clear message.

**Shared authZ dependency:** one `require_session(session_id, x_session_token)` dependency used by
`GET /sessions/{id}`, `GET .../messages`, `POST .../messages`, and `GET .../stream` — do not re-implement
the token comparison per route. It uses `secrets.compare_digest`, and returns the same 404 for
"unknown session" and "wrong token" so the endpoint cannot be used to enumerate session ids.

**CORS:** add `CORSMiddleware` in `create_app()` driven by `settings.cors_origins_list()`
(`allow_credentials=False`, `allow_headers=["X-Session-Token", "Content-Type"]`,
`allow_methods=["GET", "POST"]`). Empty list → middleware not added. Never `allow_origins=["*"]`
together with credentials. Without this, running Vite on `:5173` against the API on `:8000` fails
in the browser even though curl works.

**DB session lifetime for SSE:** the `POST .../messages` route passes the `async_sessionmaker` into
the generator, which opens its own session with `async with sessionmaker() as db:` and commits inside
its own `finally`, rather than taking an `AsyncSession` via `Depends`.

> Verified during execution: a mutation test that switched this route to a `Depends`-provided session
> still passed the integration suite, so on the pinned FastAPI version yield-dependency teardown does
> happen after the streaming body is sent. The generator-owned session is kept anyway — it makes the
> lifetime explicit and does not depend on teardown ordering, which has changed across FastAPI
> versions — but it is a robustness choice, not a bug fix. Do not restate the original claim.

- [x] **Step 1: Wire routers + `require_session` dependency + CORS middleware; keep health**

- [x] **Step 2: Verify the SSE route persists the final message** (integration coverage lands in Task 11; here just make sure the session is generator-owned, not `Depends`-owned)

- [x] **Step 3: Commit**

```bash
git commit -m "feat(api): expose sessions, SSE chat, and LLM probe HTTP API"
```

> If `curl -N -X POST .../messages` streams fine but the browser shows nothing: check CORS first, then
> that no proxy is buffering (`proxy_buffering off`, `X-Accel-Buffering: no` response header).

---

### Task 10: Docker Compose — db + api

**Files:**
- Create: `apps/api/Dockerfile`
- Create: `apps/api/.dockerignore`
- Create: `docker-compose.yml`
- Modify: `.env.example` (ensure Compose var names match)

**Dockerfile (api) sketch:**
- multi-stage, `uv sync --frozen` (generate lock in task: `uv lock`)
- non-root user
- CMD: alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
- `PYTHONPATH=/app/src` or install package

**`.dockerignore` (api) — required before the first build:**

```
.env
.env.*
!.env.example
.venv/
__pycache__/
.pytest_cache/
.ruff_cache/
.mypy_cache/
*.egg-info/
tests/
```

Without it the build context carries `.env` into an image layer — a leak that survives even if the file
is deleted in a later layer.

**Compose:**
- `db`: `postgres:16`, healthcheck `pg_isready`, named volume
- `api`: build `apps/api`, `depends_on: db: condition: service_healthy`, `env_file: .env`
- `api` healthcheck (the Definition of Done says "healthy" — give it something to report):
  ```yaml
  healthcheck:
    test: ["CMD-SHELL", "python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/v1/health').status==200 else 1)\""]
    interval: 10s
    timeout: 3s
    retries: 5
    start_period: 20s
  ```
  (no `curl` in a slim image — use the interpreter that is already there)
- ports: `8000:8000` for local / Claude Code smoke

- [x] **Step 1: `uv lock` in `apps/api`**

- [x] **Step 2: Write `.dockerignore` + Dockerfile + compose**

- [x] **Step 3: Build & health (local / Claude Code)**

```bash
docker compose up --build -d db api
curl -sf http://localhost:8000/api/v1/health
docker compose ps            # api must report (healthy), not just Up
```

Expected: `{"status":"ok"}`

- [x] **Step 4: Verify no `.env` in the image**

```bash
docker compose run --rm --entrypoint sh api -c 'ls -a /app | grep -c "^\.env$" || echo "clean"'
```

Expected: `clean`

- [x] **Step 5: Commit**

```bash
git commit -m "chore: add API Dockerfile and Compose for db+api"
```

---

### Task 11: Integration SSE test (Postgres)

**Files:**
- Create: `apps/api/tests/integration/conftest.py`
- Create: `apps/api/tests/integration/test_api_sse.py`

**Approach:** Use Compose Postgres URL from env `DATABASE_URL` (local Claude Code machine) or skip if unavailable:

```python
pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")
```

> The skip guard means these tests run **only** when someone opts in. CI (Task 14) must set
> `RUN_INTEGRATION=1`, otherwise this suite silently never executes.

**`conftest.py` responsibilities (do not skip — an empty database fails every test):**

1. Session-scoped fixture that runs `alembic upgrade head` against `DATABASE_URL` before any test
   (`command.upgrade(Config("alembic.ini"), "head")` from `alembic.config`, or a subprocess call).
   Never `Base.metadata.create_all()` — migrations are the schema source of truth (Task 5).
2. Per-test isolation: `TRUNCATE messages, sessions RESTART IDENTITY CASCADE` between tests.
3. Force `USE_FAKE_LLM=true` via `monkeypatch.setenv` **before** `create_app()` is called, and clear the
   `Settings` cache if it is memoised — otherwise the test picks up whatever is in the ambient `.env`.
4. Use `httpx.AsyncClient(transport=ASGITransport(app=...))` — `TestClient` cannot consume a long-lived
   SSE body cleanly.

Test:
1. Create session → `{id, access_token}`
2. POST message with Fake LLM forced via `USE_FAKE_LLM=true`
3. Parse SSE: expect `model` then `token`+ then `message_end` with the same `model_id`
4. GET messages → assistant row has non-empty content **and** `model_id` after the stream closes
5. Wrong / missing `X-Session-Token` → 404, and no message is persisted

- [x] **Step 1: Implement + run with `RUN_INTEGRATION=1 USE_FAKE_LLM=true`**

- [x] **Step 2: Commit**

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

- [x] **Step 1: Scaffold Vite React-TS (non-interactive)**

`npm create vite@latest .` **prompts** when the target directory is not empty, and the agent cannot answer
an interactive prompt. Scaffold into a fresh directory, then move the result:

```bash
mkdir -p apps
rm -rf apps/web
npm create vite@latest apps/web -- --template react-ts   # apps/web must not exist beforehand
cd apps/web && npm install
```

If the prompt appears anyway, abort and write `package.json`, `vite.config.ts`, `tsconfig.json`,
`index.html`, `src/main.tsx` by hand — they are all in the file map.

`vite.config.ts` gets a dev proxy so browser dev works without CORS as well:

```ts
server: { proxy: { "/api": { target: "http://localhost:8000", changeOrigin: true } } }
```

- [x] **Step 2: Implement Chat + Probe**

SSE parsing notes (`src/api/client.ts`): `EventSource` cannot issue POST — use
`fetch(..., {method: "POST"})` and read `res.body.getReader()`. Keep a string buffer across reads and only
process complete `\n\n`-delimited event blocks; an `event:`/`data:` pair can be split across two network
chunks. Render `model_id` from the `model` event immediately and overwrite it from `message_end`.
On `event: error`, keep whatever text arrived and show an inline failure marker on that bubble.

- [x] **Step 3: Commit**

```bash
git commit -m "feat(web): add chat SPA with SSE and model_id labels"
```

---

### Task 13: Web Docker + nginx proxy + full Compose

**Files:**
- Create: `apps/web/Dockerfile`
- Create: `apps/web/.dockerignore`
- Create: `apps/web/nginx.conf`
- Modify: `docker-compose.yml` add `web`

**`.dockerignore` (web):** `node_modules/`, `dist/`, `.env`, `.env.*` (`!.env.example`).

**`VITE_API_URL` is build-time, not runtime.** Vite inlines `import.meta.env.*` during `npm run build`, so
passing it as a Compose `environment:` entry to the nginx image does nothing. In the prod-like image the
app must rely on the default relative `/api/v1` and let nginx proxy it. If an absolute URL is ever needed,
pass it as a Docker `ARG VITE_API_URL` in the build stage — and say so in `.env.example`.

**nginx.conf:**
- serve `/usr/share/nginx/html`, SPA fallback `try_files $uri /index.html`
- ```nginx
  location /api/ {
      proxy_pass http://api:8000/api/;
      proxy_http_version 1.1;
      proxy_buffering off;          # SSE: do not buffer the token stream
      proxy_cache off;
      proxy_read_timeout 3600s;     # a long answer must not be cut at the default 60s
      proxy_set_header Connection "";
  }
  ```

- [ ] **Step 1: Multi-stage web image**

- [ ] **Step 2: `docker compose up --build -d`**

- [ ] **Step 3: Manual smoke — open web, send message (Fake or real), confirm model label**

Also confirm tokens arrive **incrementally** (not all at once at the end) — a single late burst means nginx
or the proxy is still buffering.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(web): Docker/nginx proxy and wire full Compose stack"
```

---

### Task 14: CI — lint, types, unit + integration tests

**Files:**
- Create: `.github/workflows/ci.yml`

**Why:** the integration suite is gated behind `RUN_INTEGRATION` (Task 11). Without a job that sets it,
those tests never run anywhere. CI is also the only place that proves the keyless path really works.

**Workflow shape:**

- Trigger: `push` + `pull_request`
- Single `api` job, `ubuntu-latest`, with a `postgres:16` **service container** (`POSTGRES_*` are throwaway
  CI values, not secrets — but still passed as `env:`, never inlined into a command that gets echoed)
- Steps: `astral-sh/setup-uv` → `uv sync --frozen` → `uv run ruff check .` → `uv run ruff format --check .`
  → `uv run mypy src` → `uv run pytest tests/unit` → `uv run pytest tests/integration`
- Integration step env: `RUN_INTEGRATION=1`, `USE_FAKE_LLM=true`,
  `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres`
- A `web` job: `npm ci` → `npx tsc --noEmit` → `npm run build`
- **No `LLM_API_KEY` anywhere in CI for v1** — the whole suite must be green without a provider key. If a
  live smoke job is added later it belongs in a separate, manually-triggered workflow reading a repository
  secret, never in the default push workflow.

- [ ] **Step 1: Write the workflow**

- [ ] **Step 2: Verify it passes locally first**

```bash
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest tests/unit -v
cd ../web && npx tsc --noEmit && npm run build
```

- [ ] **Step 3: Confirm the workflow file contains no secret values and no `.env` reference**

- [ ] **Step 4: Commit**

```bash
git commit -m "ci: add lint, type-check, and test workflow"
```

---

### Task 15: README + Claude Code checklist + status polish

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md` status → `Implemented (v1 plan executed)` only if done; otherwise leave and point to this plan
- Ensure `.gitignore` / `.cursorignore` / `.env.example` complete

**README must include:**
- Architecture one-liner + link to spec + this plan
- `docker compose up --build`
- Env var table (names only) + Claude Code starter prompt pointer
- `USE_FAKE_LLM=true` for keyless demo
- Two dev modes: full Docker (nginx proxies `/api`) vs local Vite on `:5173` + API on `:8000`
  (needs `CORS_ALLOW_ORIGINS` or the Vite dev proxy)
- Known v1 limits, stated plainly: failover only before the first token; `GET .../stream` replays a stored
  message rather than resuming a live one; router exhaustion state is per-process
- Explicit: never commit `.env`; never paste keys into Claude Code chat

- [ ] **Step 1: Write README**

- [ ] **Step 2: Final verification checklist (Claude Code)**

```bash
docker compose ps                       # db, api, web — api must be (healthy)
curl -sf http://localhost:8000/api/v1/health
cd apps/api && uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv run pytest tests/unit -v
RUN_INTEGRATION=1 USE_FAKE_LLM=true uv run pytest tests/integration -v
```

- [ ] **Step 3: Confirm `git status` has no `.env`, and no image ships one**

```bash
git status --porcelain | grep -E '(^|/)\.env($|[^.])' && echo "LEAK" || echo "clean"
docker compose run --rm --entrypoint sh api -c 'ls -a /app | grep -c "^\.env$" || echo "clean"'
```

- [ ] **Step 4: Commit**

```bash
git commit -m "docs: add Claude Code–oriented README and run checklist"
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
| Secrets / Claude Code / no .env in git or images | Global + 4, 10, 13, 14, 15 |
| Domain-agnostic naming | Global + 6 |
| Unit + SSE integration tests | 3, 7, 8, 11 |
| CORS / two dev modes | 4, 9, 12, 15 |
| Failover semantics (pre-first-token only) | Global + 3, 8 |
| Disconnect / partial-answer persistence | 8, 11 |
| History + message-size limits | 4, 8 |
| Lint, types, CI | 1, 14 |

## Out of scope (do not implement in this plan)

Auth, admin scenario UI, Redis router state, voice, billing, microservices, clinical default prompts.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md`.

**Primary:** run in **Claude Code** (Anthropic account) with the starter prompt above after you create local `.env` yourself.

**Also possible in Cursor (this IDE):**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks  
2. **Inline Execution** — execute tasks in this session with checkpoints  

Do not confuse with Cursor Cloud Agents — this plan targets Claude Code on your machine / Claude account.
