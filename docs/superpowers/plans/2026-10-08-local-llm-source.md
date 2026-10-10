# Local LLM source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in user connects the M1 Ollama at `http://100.90.210.109:11435` in Profile → Подключения, pins `ollama/qwen36-fast:latest` (35.5B Q4_K_M, the SkyNet fallback tag), and gets chat, Agent 07, and week-6 RAG answers from that model with `model_id` on the bubble. When `ssh -N kalinin-gpu` is up, the same form accepts `http://127.0.0.1:21434` (the LocalForward onto the GPU box Ollama).

**Architecture:** Postgres stores one origin per user. The HTTP layer loads that row and binds it in a `ContextVar` for the duration of the stream. `RoutingLLMProvider` sits inside the existing `ModelRouter`: cloud ids stay on `OpenAICompatibleProvider`; `ollama/…` goes to native `POST /api/chat` with `think: false`. AUTO never selects a local model. RAG retrieval is unchanged.

**Tech Stack:** FastAPI, Alembic, httpx, existing `ModelRouter` / `GenerationParams`, Vite React profile panel.

**Spec:** `docs/superpowers/specs/2026-10-08-local-llm-source-design.md`

## Global Constraints

- Domain-agnostic names only. No patient/doctor wording.
- Every assistant reply still exposes resolved `model_id` (DB, SSE, UI). Local ids are `ollama/<tag>`.
- Never read or commit `.env`. New names only: `LOCAL_LLM_ALLOW_LOOPBACK`, `LOCAL_LLM_ALLOW_TAILSCALE`, `LOCAL_LLM_ALLOW_PRIVATE`.
- Do not change xray, Reality, public `:443` / `:8443`, or run `docker compose down`.
- Do not point `LLM_BASE_URL` at a laptop. Cloud chain behavior stays when the pin is not `ollama/`.
- `USE_FAKE_LLM=true` suite stays green.
- API key column is write-only. Analytics and list DTOs carry host and model count, never the key and never the full URL.
- A failed `ollama/` pin does not fall through to the cloud chain.
- `num_ctx` and a second quantization are out of scope. `qwen36-fast:latest` is already Q4_K_M. This Mac's `qwen3:8b` / `llama3.1:8b` are not the graded model.
- An `ollama/` pin uses a 90 s first-token budget. The cloud chain stays at 25 s.
- M1 reachability requires `LOCAL_LLM_ALLOW_TAILSCALE=true`. Loopback covers `127.0.0.1:21434` after the kalinin SSH forward.
- Do not re-embed the stand index. Day 28 may still use `EMBEDDING_PROVIDER=api`.
- No production deploy in this plan.

---

## File map

**Create**

- `apps/api/src/app/domain/local_llm.py` — URL policy, id prefix, source dataclass, scope `ContextVar`
- `apps/api/src/app/adapters/llm/ollama_native.py` — native `/api/chat` and `/api/tags`
- `apps/api/src/app/adapters/llm/routing_provider.py` — cloud vs `ollama/`
- `apps/api/src/app/application/local_llm.py` — connect / disconnect
- `apps/api/src/app/adapters/persistence/local_llm_repo.py` — Postgres
- `apps/api/src/app/adapters/api/local_llm.py` — `/me/llm-sources`
- `apps/api/alembic/versions/013_user_llm_sources.py`
- `apps/api/tests/unit/test_local_llm_url.py`
- `apps/api/tests/unit/test_ollama_native.py`
- `apps/api/tests/unit/test_routing_llm_provider.py`
- `apps/api/tests/unit/test_local_llm_connect.py`
- `apps/web/src/components/profile/LocalLlmPanel.tsx`
- `challenges/26-local-llm/` … `challenges/29-local-optimize/` — README, RESULTS, VIDEO, `run.py`

**Modify**

- `apps/api/src/app/core/settings.py` — three allow flags, default loopback on
- `apps/api/src/app/core/deps.py` — wrap the built provider in `RoutingLLMProvider`
- `apps/api/src/app/adapters/api/llm.py` — merge catalog; bind scope around probe
- `apps/api/src/app/adapters/api/sessions.py` — bind scope inside the message stream
- `apps/api/src/app/adapters/api/agent_workshop.py` — bind scope around workshop runs
- `apps/api/src/app/adapters/api/agent_battle.py` — bind scope inside battle frames
- `apps/api/src/app/main.py` — include the new router
- `apps/web/src/api/client.ts` — connect / get / delete
- `apps/web/src/components/profile/ProfilePanel.tsx` — render the panel under Подключения
- `.env.example` — the three flag names, empty of secrets
- `challenges/README.md` — rows 26–29

---

### Task 1: URL policy and catalog ids

**Files:**
- Create: `apps/api/src/app/domain/local_llm.py`
- Create: `apps/api/tests/unit/test_local_llm_url.py`
- Modify: `apps/api/src/app/core/settings.py`
- Test: `apps/api/tests/unit/test_local_llm_url.py`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `LOCAL_LLM_PREFIX = "ollama/"`
  - `canonical_model_id(upstream: str) -> str` → `ollama/qwen36-fast:latest`
  - `upstream_model_id(model_id: str) -> str | None`
  - `canonicalize_ollama_origin(url: str, *, allow_loopback: bool, allow_tailscale: bool, allow_private: bool) -> str`
  - `class LocalLlmUrlError(ValueError)` with `.message`
  - `@dataclass(frozen=True) class LocalLlmSource` fields: `user_id: UUID`, `name: str`, `base_url: str`, `api_key: str | None`, `enabled: bool`, `models: tuple[str, ...]`, `status: str`, `safe_error: str | None`
  - `set_local_llm_source(source: LocalLlmSource | None) -> Token`, `reset_local_llm_source(token: Token) -> None`, `current_local_llm_source() -> LocalLlmSource | None`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from app.domain.local_llm import (
    LocalLlmUrlError,
    canonical_model_id,
    canonicalize_ollama_origin,
    upstream_model_id,
)


def test_catalog_id_round_trip() -> None:
    assert canonical_model_id("qwen36-fast:latest") == "ollama/qwen36-fast:latest"
    assert upstream_model_id("ollama/qwen36-fast:latest") == "qwen36-fast:latest"
    assert upstream_model_id("deepseek/deepseek-v4-flash") is None


def test_loopback_only_with_flag() -> None:
    with pytest.raises(LocalLlmUrlError):
        canonicalize_ollama_origin(
            "http://127.0.0.1:11434",
            allow_loopback=False,
            allow_tailscale=False,
            allow_private=False,
        )
    assert (
        canonicalize_ollama_origin(
            "http://127.0.0.1:11434/v1/",
            allow_loopback=True,
            allow_tailscale=False,
            allow_private=False,
        )
        == "http://127.0.0.1:11434"
    )


def test_tailscale_cgnat_needs_its_own_flag() -> None:
    with pytest.raises(LocalLlmUrlError):
        canonicalize_ollama_origin(
            "http://100.90.210.109:11435",
            allow_loopback=True,
            allow_tailscale=False,
            allow_private=False,
        )
    assert (
        canonicalize_ollama_origin(
            "http://100.90.210.109:11435",
            allow_loopback=False,
            allow_tailscale=True,
            allow_private=False,
        )
        == "http://100.90.210.109:11435"
    )


def test_metadata_always_blocked() -> None:
    with pytest.raises(LocalLlmUrlError):
        canonicalize_ollama_origin(
            "http://169.254.169.254:11434",
            allow_loopback=True,
            allow_tailscale=True,
            allow_private=True,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_local_llm_url.py -v`
Expected: FAIL, `local_llm` import error

- [ ] **Step 3: Implement policy**

`canonicalize_ollama_origin` parses with `urllib.parse.urlparse`, requires `http` or `https`, drops any path/query, requires a host. `host.docker.internal` is allowed only when `allow_loopback` is true. Literal IPs: reject link-local and `169.254.169.254`; allow loopback only with `allow_loopback`; allow `ipaddress.ip_network("100.64.0.0/10")` only with `allow_tailscale`; allow `ip.is_private` only with `allow_private`. Hostnames that are not special-cased are accepted only as `https` (public). `canonical_model_id` rejects empty tags, whitespace, and tags containing `/`.

Add settings fields, defaults: `local_llm_allow_loopback: bool = True`, `local_llm_allow_tailscale: bool = False`, `local_llm_allow_private: bool = False`. Document the names in `.env.example` with a one-line comment. No values.

`ContextVar` default is `None`. `set` / `reset` / `current` are thin wrappers. A unit test in the same file sets a dummy source and asserts `reset` restores `None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_local_llm_url.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/app/domain/local_llm.py apps/api/src/app/core/settings.py apps/api/tests/unit/test_local_llm_url.py .env.example
git commit -m "feat: add Ollama origin policy and ollama/ model ids"
```

---

### Task 2: Native Ollama provider

**Files:**
- Create: `apps/api/src/app/adapters/llm/ollama_native.py`
- Create: `apps/api/tests/unit/test_ollama_native.py`
- Test: `apps/api/tests/unit/test_ollama_native.py`

**Interfaces:**
- Consumes: `canonical_model_id`, `GenerationParams`, `ChatMessage`, `TokenChunk`, `CompletionResult`
- Produces:
  - `class OllamaNativeProvider` with `complete_chat` and `stream_chat` matching `LLMProvider`
  - `async def fetch_ollama_tags(origin: str, api_key: str | None, *, client: httpx.AsyncClient) -> tuple[str, ...]`

- [ ] **Step 1: Write the failing test**

Use `httpx.MockTransport`. The handler records the JSON body and returns one JSON object for `/api/chat`:

```python
{"message": {"role": "assistant", "content": "Имя: Артем\nЯзык: Python"}, "done": true, "model": "qwen36-fast:latest"}
```

```python
async def test_complete_sends_think_false_and_rewrites_model_id() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": "Имя: Артем\nЯзык: Python"},
            "done": True,
            "model": "qwen36-fast:latest",
        })

    provider = OllamaNativeProvider(
        "http://127.0.0.1:11434",
        api_key=None,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="память")],
        "ollama/qwen36-fast:latest",
        generation=GenerationParams(temperature=0.15, max_tokens=40),
    )
    assert result.model_id == "ollama/qwen36-fast:latest"
    assert result.content.startswith("Имя: Артем")
    assert seen["body"]["think"] is False
    assert seen["body"]["model"] == "qwen36-fast:latest"
    assert seen["body"]["options"]["temperature"] == 0.15
    assert seen["body"]["options"]["num_predict"] == 40
    assert "Authorization" not in handler  # header absence checked via request in handler
```

Add a second assertion inside the handler: `assert "authorization" not in {k.lower() for k in request.headers}` when `api_key` is `None`. A third test passes `api_key="ollama"` and expects `Bearer ollama`. A fourth test: `generation=GenerationParams(reasoning=True)` sends `"think": True`.

`/api/tags` test returns `{"models": [{"name": "qwen36-fast:latest"}, {"name": "llama3.1:8b"}]}` and expects that tuple.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_ollama_native.py -v`
Expected: FAIL, import error

- [ ] **Step 3: Implement the provider**

`complete_chat` POSTs `{origin}/api/chat` with `stream: false`, `think` from `generation.reasoning` (default false), `model` = `upstream_model_id` or the raw name if it has no prefix, `messages` as `{role, content}`, `options` only for set knobs: `temperature`, `num_predict` from `resolved_max_tokens()`, `stop`. Read `message.content`. If content is empty, raise `LLMProviderError` kind `empty` with `model_id` already rewritten to `canonical_model_id`. Never return the bare Ollama name.

`stream_chat` POSTs `stream: true` and parses NDJSON lines. Yield `TokenChunk(text=delta, model_id=canonical)` for each non-empty `message.content`. Ignore `message.thinking` / `message.reasoning` so a thinking model cannot look like answer text.

`fetch_ollama_tags` GETs `{origin}/api/tags`, timeout 8 s, returns names. Non-200 becomes `LLMProviderError` kind `transport` with a safe message `Ollama не ответил на /api/tags`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_ollama_native.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/app/adapters/llm/ollama_native.py apps/api/tests/unit/test_ollama_native.py
git commit -m "feat: call Ollama native chat with think disabled"
```

---

### Task 3: Routing provider inside the existing router

**Files:**
- Create: `apps/api/src/app/adapters/llm/routing_provider.py`
- Create: `apps/api/tests/unit/test_routing_llm_provider.py`
- Modify: `apps/api/src/app/core/deps.py` (`build_container` provider assignment)
- Test: `apps/api/tests/unit/test_routing_llm_provider.py`

**Interfaces:**
- Consumes: `OllamaNativeProvider`, `current_local_llm_source`, `FakeLLMProvider` or any `LLMProvider`
- Produces: `class RoutingLLMProvider(cloud: LLMProvider)` implementing `LLMProvider`. For `ollama/` it builds `OllamaNativeProvider(source.base_url, source.api_key)` from the context var. No source or tag missing from `source.models` → `LLMProviderError` kind `config`, message `Подключите локальную модель в Профиле.`, `model_id` set to the requested id. It does not call `cloud`.

- [ ] **Step 1: Write the failing test**

```python
async def test_cloud_pin_does_not_touch_ollama() -> None:
    cloud = FakeLLMProvider(text="cloud")
    router_provider = RoutingLLMProvider(cloud)
    result = await router_provider.complete_chat(
        [ChatMessage(role=MessageRole.USER, content="hi")],
        "model-a",
    )
    assert result.content == "cloud"
    assert result.model_id == "model-a"


async def test_ollama_pin_without_scope_does_not_call_cloud() -> None:
    cloud = FakeLLMProvider(text="cloud")
    provider = RoutingLLMProvider(cloud)
    with pytest.raises(LLMProviderError) as exc:
        await provider.complete_chat(
            [ChatMessage(role=MessageRole.USER, content="hi")],
            "ollama/qwen36-fast:latest",
        )
    assert exc.value.model_id == "ollama/qwen36-fast:latest"
    assert "Профиле" in exc.value.message
```

Third test: set a `LocalLlmSource` whose `models` is `("qwen36-fast:latest",)` and whose base URL is the mock transport origin; assert content comes from the mock and `model_id == "ollama/qwen36-fast:latest"`. Fourth test: source models are `("llama3.1:8b",)` and the pin is `ollama/qwen36-fast:latest` → config error, cloud text is not returned.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_routing_llm_provider.py -v`
Expected: FAIL, import error

- [ ] **Step 3: Wrap the container provider**

Implement `RoutingLLMProvider`. In `build_container`, after `provider` is created (both the FakeLLM branch and the OpenAI branch), replace it with `RoutingLLMProvider(provider)` before `_router_for`. The fallback tier provider stays a plain cloud provider: fallback is the cloud safety net, and an `ollama/` pin must not be retried there. `ModelRouter` first-token timeout stays 25 s for cloud ids. When the candidate starts with `ollama/`, pass 90 s into that attempt only. `ModelRouter._candidates` already pins an unknown id first; when that attempt raises `LLMProviderError` with kind `config`, confirm the router does not continue. If it does continue today, catch kind `config` in `RoutingLLMProvider` only — the router must see a non-retryable error. Read `ModelRouter.complete_chat`: retryable kinds are quota/timeout/empty. `config` is not in that set, so the chain stops. Add a unit test through `ModelRouter(RoutingLLMProvider(FakeLLMProvider()), ["cloud-model"])` pinned to `ollama/qwen36-fast:latest` asserting the exception and that the fake cloud text was not returned.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_routing_llm_provider.py tests/unit/test_settings.py -v`
Expected: PASS. Then `cd apps/api && uv run pytest tests/unit -q` and confirm the existing FakeLLM suite is still green.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/app/adapters/llm/routing_provider.py apps/api/src/app/core/deps.py apps/api/tests/unit/test_routing_llm_provider.py
git commit -m "feat: route ollama/ pins away from the cloud chain"
```

---

### Task 4: Persist the source and connect it

**Files:**
- Create: `apps/api/alembic/versions/013_user_llm_sources.py` (`revision = "013"`, `down_revision = "012"`)
- Create: `apps/api/src/app/adapters/persistence/local_llm_repo.py`
- Create: `apps/api/src/app/application/local_llm.py`
- Create: `apps/api/src/app/adapters/api/local_llm.py`
- Create: `apps/api/tests/unit/test_local_llm_connect.py`
- Modify: `apps/api/src/app/main.py` — `include_router`
- Modify: `apps/api/src/app/adapters/api/llm.py`, `sessions.py`, `agent_workshop.py`, `agent_battle.py`
- Test: `apps/api/tests/unit/test_local_llm_connect.py`

**Interfaces:**
- Consumes: `canonicalize_ollama_origin`, `fetch_ollama_tags`, `LocalLlmSource`, `set_local_llm_source` / `reset_local_llm_source`
- Produces:
  - `async def connect_local_llm(user_id: UUID, *, name: str, base_url: str, api_key: str | None, settings: Settings, repo, tags) -> LocalLlmPublic`
  - `async def disconnect_local_llm(user_id: UUID, repo) -> None`
  - `LocalLlmPublic` fields: `name`, `base_host`, `status`, `models: tuple[str, ...]`, `enabled`. No `api_key`, no full URL.
  - `GET/PUT/DELETE /api/v1/me/llm-sources` (auth required)
  - helper `async with local_llm_scope(source): ...` used by the four HTTP entrypoints

- [ ] **Step 1: Write the failing test**

In-memory repo double. Tags client returns `("qwen36-fast:latest",)`. Settings with `allow_loopback=True`.

```python
async def test_connect_stores_origin_and_hides_key() -> None:
    repo = InMemoryLocalLlmRepo()
    public = await connect_local_llm(
        USER_ID,
        name="Mac",
        base_url="http://127.0.0.1:11434/v1",
        api_key="secret-value",
        settings=_settings(local_llm_allow_loopback=True),
        repo=repo,
        tags=FakeTags(("qwen36-fast:latest",)),
    )
    assert public.base_host == "127.0.0.1"
    assert public.models == ("qwen36-fast:latest",)
    dumped = json.dumps(public.__dict__)
    assert "secret-value" not in dumped
    stored = await repo.get_for_user(USER_ID)
    assert stored is not None
    assert stored.base_url == "http://127.0.0.1:11434"
    assert stored.api_key == "secret-value"
```

Second test: `http://169.254.169.254:11434` raises `LocalLlmUrlError` and the repo stays empty. Third test: second connect for the same user replaces the row (still one row).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_local_llm_connect.py -v`
Expected: FAIL, import error

- [ ] **Step 3: Migration, repo, use case, routes, scope binding**

Migration columns match the spec table. `models_json` is `Text`. Unique on `user_id`.

`connect_local_llm` canonicalizes, fetches tags, upserts `status="connected"`. Tag fetch failure stores nothing and raises `LLMProviderError` kind `transport` with `Ollama недоступен по этому адресу`.

Routes under prefix `/me`, tag `local-llm`, `require_auth_user`. PUT body: `name`, `base_url`, optional `api_key`. Response is `LocalLlmPublic`. DELETE returns 204. GET returns the public row or `null`.

Catalog: `GET /llm/models` takes `OptionalAuthUser` and, when a connected source exists, appends `canonical_model_id(tag)` for each cached tag after the env chain. Labels stay the full id.

Scope binding, because a `StreamingResponse` can outlive a yield dependency: load the row in the endpoint, then set the context var **inside** the generator / around the awaited run, and reset in `finally`.

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def local_llm_scope(source: LocalLlmSource | None):
    token = set_local_llm_source(source if source and source.enabled else None)
    try:
        yield
    finally:
        reset_local_llm_source(token)
```

Call sites that must wrap the LLM call:

- `sessions.py` message `frames()` — the generator that calls `send_user_message_and_stream`
- `llm.py` `complete` — both the non-stream `complete_probe` await and the stream `frames()`
- `agent_workshop.py` — each route that calls `run_agent` / `run_agent_with_dialog`
- `agent_battle.py` `frames()` — add `OptionalAuthUser` so the row can be loaded

Load with `SqlAlchemyLocalLlmSourceRepository(db).get_for_user`. Anonymous → `source=None`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/unit/test_local_llm_connect.py tests/unit/test_routing_llm_provider.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/alembic/versions/013_user_llm_sources.py apps/api/src/app/application/local_llm.py apps/api/src/app/adapters/persistence/local_llm_repo.py apps/api/src/app/adapters/api/local_llm.py apps/api/src/app/adapters/api/llm.py apps/api/src/app/adapters/api/sessions.py apps/api/src/app/adapters/api/agent_workshop.py apps/api/src/app/adapters/api/agent_battle.py apps/api/src/app/main.py apps/api/tests/unit/test_local_llm_connect.py
git commit -m "feat: save a per-user Ollama source and bind it to the request"
```

---

### Task 5: Profile → Подключения panel

**Files:**
- Create: `apps/web/src/components/profile/LocalLlmPanel.tsx`
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/components/profile/ProfilePanel.tsx` (connections section, next to Guest MCP)
- Test: manual on local web plus typecheck

**Interfaces:**
- Consumes: `PUT/GET/DELETE /api/v1/me/llm-sources`, existing `listModels()`
- Produces: form fields name, base URL, optional key; status line with host and model count; after save, `ollama/…` appears in Profile → Модели because `listModels()` already feeds that select

- [ ] **Step 1: Write the client functions**

```typescript
export type LocalLlmSourceDto = {
  name: string;
  base_host: string;
  status: "connected" | "error" | "off";
  models: string[];
  enabled: boolean;
};

export function getLocalLlmSource() {
  return request<LocalLlmSourceDto | null>("/me/llm-sources");
}

export function putLocalLlmSource(body: { name: string; base_url: string; api_key?: string }) {
  return request<LocalLlmSourceDto>("/me/llm-sources", { method: "PUT", body: JSON.stringify(body) });
}

export function deleteLocalLlmSource() {
  return request<void>("/me/llm-sources", { method: "DELETE" });
}
```

- [ ] **Step 2: Panel copy**

Title: «Локальная модель (Ollama)». Hint under the URL field: «M1 SkyNet: http://100.90.210.109:11435 (нужен LOCAL_LLM_ALLOW_TAILSCALE). Калинин при поднятом ssh -N kalinin-gpu: http://127.0.0.1:21434. Этот Mac: http://127.0.0.1:11434.» Do not mention production IPs. Empty key is allowed. On success, show `base_host` and `models.length`. The key input is write-only and is not filled from GET.

Wire the panel into the `connections` branch of `ProfilePanel` for a logged-in user. Logged-out users keep the existing gate.

- [ ] **Step 3: Typecheck**

Run: `cd apps/web && npx tsc --noEmit`
Expected: exit 0

- [ ] **Step 4: Browser check when a local API is up**

Sign in, open Profile → Подключения, save `http://100.90.210.109:11435`, confirm the model select lists `ollama/qwen36-fast:latest`, send «Запомни: имя Артем, язык Python. Ответь двумя строками Имя: и Язык:», confirm the bubble badge is `ollama/qwen36-fast:latest` and the lines match. If the API is not running, say so and stop; do not deploy. The first reply may sit inside the 90 s local budget while the 22 GB tag loads.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/api/client.ts apps/web/src/components/profile/LocalLlmPanel.tsx apps/web/src/components/profile/ProfilePanel.tsx
git commit -m "feat: connect Ollama from profile settings"
```

---

### Task 6: Course folders 26–29

**Files:**
- Create: `challenges/26-local-llm/README.md`, `run.py`, `RESULTS.md`, `VIDEO.md`
- Create: `challenges/27-local-app/README.md`, `VIDEO.md`, `RESULTS.md`
- Create: `challenges/28-local-rag/README.md`, `VIDEO.md`, `RESULTS.md`
- Create: `challenges/29-local-optimize/README.md`, `run.py`, `RESULTS.md`, `VIDEO.md`
- Modify: `challenges/README.md` — four rows
- Test: `python3 challenges/26-local-llm/run.py --score-only`

**Interfaces:**
- Consumes: native Ollama on `http://100.90.210.109:11435`, model `qwen36-fast:latest`, when a human runs the full script; `--score-only` needs no daemon
- Produces: the three prompts from the spec, and a faithfulness score used by day 29

- [ ] **Step 1: Score function and offline test**

In `challenges/26-local-llm/run.py`:

```python
PROMPTS = {
    "easy": "Запомни на этот ход: имя Артем, язык Python. Ответь ровно двумя строками:\nИмя: …\nЯзык: …",
    "medium": "Что такое model_id в ответах ассистента на стенде AIChallenge? Два предложения.",
    "hard": "Куда ходит публичный порт 443 на стенде AIChallenge и можно ли делать docker compose down на проде? Ответь точно, с портами.",
}

def score(kind: str, text: str) -> int:
    low = text.lower()
    if kind == "easy":
        return 2 if ("артем" in low and "python" in low) else 0
    if kind == "medium":
        surfaces = sum(s in low for s in ("api", "sse", "ui", "db"))
        return 2 if surfaces >= 2 else (1 if "model" in low else 0)
    ports = "443" in text and "8443" in text and "18080" in text
    forbid = any(w in low for w in ("нельзя", "запрещ"))
    if ports and forbid:
        return 2
    if ("8443" in text or "xray" in low) and forbid:
        return 1
    return 0
```

`--score-only` asserts `score("easy", "Имя: Артем\nЯзык: Python") == 2`, `score("hard", "обычный https. docker compose down --rmi all") == 0`, and `score("hard", "443 идёт в xray, затем nginx :8443. compose down нельзя") == 1`. Exit 0. No network.

- [ ] **Step 2: Run the offline score**

Run: `python3 challenges/26-local-llm/run.py --score-only`
Expected: exit 0

- [ ] **Step 3: README and video shot lists**

`26` README: curl `http://100.90.210.109:11435/api/tags` must show `qwen36-fast:latest`, then three `POST /api/chat` calls with `think: false` to that tag. Full `run.py` writes `results.json` with `wall_s` and `tokens_per_s`. `VIDEO.md`: the tag list and three answers. Mention the kalinin forward `127.0.0.1:21434` as the optional second origin, not the required one.

`27` README: Profile connect to the M1, pin `ollama/qwen36-fast:latest`, easy prompt, badge equals the pin. `VIDEO.md`: settings, bubble, Agent 07 two lines.

`28` README: same pin, hard prompt with «Использовать базу» off, then on. Expect sources footer when on. State that query embeddings may still use the API embedder; retrieval stays in `apps/rag`. `VIDEO.md`: off/on pair.

`29` README: hard prompt on `qwen36-fast:latest` twice. Before: `temperature` 0.8, `num_predict` 220, no system. After: `temperature` 0.4 (the SkyNet bot default) or 0.15, `num_predict` 180, system text from `format_rag_system_context` shape («опирайся только на фрагменты»). `run.py` prints the score table. Quant column is the string `Q4_K_M`. `VIDEO.md`: the two answers and the table. Graded model is the 35B M1 tag. The 8B tags on this Mac are not a pass.

`challenges/README.md` table gains rows 26–29 pointing at these folders and at Чат / Профиль / База.

Do not add mp4/webm files.

- [ ] **Step 4: Commit**

```bash
git add challenges/26-local-llm challenges/27-local-app challenges/28-local-rag challenges/29-local-optimize challenges/README.md
git commit -m "docs: add local LLM challenge days 26-29"
```

---

## Self-review

- Spec §2.1–2.10 map to tasks 1–5. Course days map to task 6. Out-of-scope items have no tasks.
- Empty `content` on the OpenAI shim is avoided by task 2 (`think: false`, ignore reasoning text).
- Streaming lifetime is handled by setting the `ContextVar` inside the generator (task 4), not in a yield dependency that ends when `StreamingResponse` is returned.
- Cloud fallback cannot swallow an `ollama/` pin (task 3, kind `config`).
- Placeholder scan: no TBD steps. `num_ctx` and re-embed are named as out of scope in the spec, not as later tasks inside this plan.

## Execution note

Implement on a local checkout. Do not push and do not deploy unless a later message asks for that.
