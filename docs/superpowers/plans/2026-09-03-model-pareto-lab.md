# Model Pareto Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.


> ⚠️ **Read first:** [Prep decisions](./2026-09-03-observability-prep-decisions.md) — locked technical contract from a code-reading pass.
> Where this plan and that file disagree, **the prep decisions win**.

**Goal:** Persist per-completion `RunTrace`, expose Lab Pareto aggregates API, and show a ranked table in the web Lab UI.

**Architecture:** Extend ModelRouter to record attempt history for one request; chat use-case saves a `RunTrace` via a new port after finalize; SQLAlchemy adapter + Alembic; FastAPI lab routes; web Lab float section reads `GET /lab/pareto`.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, pytest + FakeLLM, React/TS Lab UI, existing SSE chat path.

**Spec:** `docs/superpowers/specs/2026-09-03-model-pareto-lab-design.md`

## Global Constraints

- Domain-agnostic naming only (no medical role names)
- Every assistant reply still exposes resolved `model_id`
- Failover only before first token (do not change this rule)
- Never read or commit `.env` secrets; FakeLLM in CI
- Hexagonal: `domain` must not import FastAPI/SQLAlchemy/httpx
- No deploy unless user explicitly asks

## File map

| Path | Responsibility |
|------|----------------|
| `apps/api/src/app/domain/tracing.py` | `RunTrace`, `AttemptRecord`, `ModelAggregate` entities |
| `apps/api/src/app/domain/ports.py` | `RunTraceRepository` protocol |
| `apps/api/src/app/adapters/llm/router.py` | Collect attempts during `stream_chat` / `complete_chat` |
| `apps/api/src/app/application/chat.py` | Build + save trace after stream ends |
| `apps/api/src/app/application/pareto.py` | Aggregate scoring helper |
| `apps/api/src/app/adapters/persistence/models.py` | `RunTraceRow` |
| `apps/api/src/app/adapters/persistence/trace_repo.py` | Repo impl |
| `apps/api/alembic/versions/00X_run_traces.py` | Migration |
| `apps/api/src/app/adapters/api/lab.py` | `GET /lab/pareto`, `GET /sessions/{id}/traces` |
| `apps/api/src/app/core/settings.py` | `run_trace_enabled`, cost proxy map |
| `apps/web/src/components/ParetoPanel.tsx` | Ranked table UI |
| `apps/web/src/api/client.ts` | fetch helpers |
| `apps/api/tests/unit/test_pareto.py`, `test_run_trace_*.py` | Unit coverage |
| `apps/api/tests/integration/test_run_trace_sse.py` | SSE → DB |

---

### Task 1: Domain entities + port

**Files:**
- Create: `apps/api/src/app/domain/tracing.py`
- Modify: `apps/api/src/app/domain/ports.py`
- Test: `apps/api/tests/unit/test_tracing_entities.py`

**Interfaces:**
- Produces: `AttemptRecord`, `RunTrace`, `ModelAggregate`, `RunTraceRepository`

- [x] **Step 1: Write failing import test**

```python
from app.domain.tracing import AttemptRecord, RunTrace, ModelAggregate

def test_attempt_record_fields():
    a = AttemptRecord(model_id="m1", ok=False, reason="timeout", ttft_ms=None)
    assert a.model_id == "m1"
    assert a.ok is False
```

- [x] **Step 2: Run test — expect ImportError/fail**

Run: `cd apps/api && uv run pytest tests/unit/test_tracing_entities.py -v`

- [x] **Step 3: Implement entities + port method signatures**

```python
# tracing.py — dataclasses / frozen where appropriate
@dataclass(frozen=True)
class AttemptRecord:
    model_id: str
    ok: bool
    reason: str = ""
    ttft_ms: int | None = None
    error_kind: str | None = None

@dataclass
class RunTrace:
    id: UUID
    session_id: UUID
    message_id: UUID
    visitor_hash: str | None
    preferred_model: str
    resolved_model_id: str | None
    attempts: list[AttemptRecord]
    ttft_ms: int | None
    total_ms: int | None
    token_count_est: int | None
    cost_proxy: float | None
    tool_rounds: int
    tool_ok: bool | None
    status: str  # ok|error|aborted|exhausted
    created_at: datetime

@dataclass(frozen=True)
class ModelAggregate:
    model_id: str
    n: int
    success_rate: float
    p50_ttft_ms: float | None
    p50_total_ms: float | None
    avg_cost_proxy: float | None
    score: float
```

Add to `ports.py`:

```python
class RunTraceRepository(Protocol):
    async def save(self, trace: RunTrace) -> None: ...
    async def list_for_session(self, session_id: UUID) -> list[RunTrace]: ...
    async def aggregate(self, *, since: datetime, until: datetime) -> list[ModelAggregate]: ...
```

- [x] **Step 4: Tests pass**

- [x] **Step 5: Commit** `feat(domain): add RunTrace entities and port`

---

### Task 2: Router attempt journal

**Files:**
- Modify: `apps/api/src/app/adapters/llm/router.py`
- Test: `apps/api/tests/unit/test_router_attempts.py`

**Interfaces:**
- Consumes: existing `ModelRouter.stream_chat`
- Produces: per-request `attempts: list[AttemptRecord] | None` keyword on `stream_chat`/`complete_chat` (prep decision D1 — an instance buffer would interleave concurrent SSE requests on the singleton router) set per call

- [x] **Step 1: Failing test — FakeLLM first model times out kind, second succeeds; attempts length 2**

Use existing FakeLLM / router test patterns in `tests/unit/`.

- [x] **Step 2: Implement recording on retryable fail and on success (ok=True, ttft from monotonic)**

- [x] **Step 3: Tests pass; no change to failover-before-first-token semantics**

- [x] **Step 4: Commit** `feat(llm): record per-request router attempts`

---

### Task 3: Scoring helper

**Files:**
- Create: `apps/api/src/app/application/pareto.py`
- Test: `apps/api/tests/unit/test_pareto.py`

```python
def pareto_score(success_rate: float, p50_total_ms: float | None, avg_cost_proxy: float | None) -> float:
    latency_s = max((p50_total_ms or 1000.0) / 1000.0, 0.2)
    cost = max(avg_cost_proxy or 1.0, 0.01)
    return success_rate / latency_s / cost
```

- [x] Implement + unit tests for edge zeros
- [x] Commit `feat(application): pareto score helper`

---

### Task 4: Persistence + migration

**Files:**
- Modify: `apps/api/src/app/adapters/persistence/models.py`
- Create: `apps/api/src/app/adapters/persistence/trace_repo.py`
- Create: `apps/api/alembic/versions/003_run_traces.py` (use next free revision number)
- Wire: `deps.py` / session factory
- Test: unit with in-memory or existing persistence test style; integration if Postgres profile available

- [x] Table `run_traces`: UUID PK, FKs, JSONB `attempts`, timings, status, indexes on `(created_at)`, `(session_id)`
- [x] `SqlAlchemyRunTraceRepository.aggregate` computes p50 in SQL or Python (Python OK for v1 if N small)
- [x] Commit `feat(db): add run_traces table and repository`

---

### Task 5: Save trace from chat use-case

**Files:**
- Modify: `apps/api/src/app/application/chat.py`
- Modify: `apps/api/src/app/core/deps.py`, `settings.py`
- Test: unit with fake repos

- [x] After `MessageEndEvent` / abort / exhausted / provider error paths, if `run_trace_enabled`, `save(RunTrace(...))`
- [x] `cost_proxy` from settings map by `resolved_model_id`
- [x] `token_count_est = max(1, len(content) // 4)`
- [x] Failures saving trace must **log and not fail** the user SSE
- [x] Commit `feat(chat): persist RunTrace after completion`

---

### Task 6: Lab API

**Files:**
- Create or extend: `apps/api/src/app/adapters/api/lab.py` (presets already under lab)
- Register router in `main.py`
- Test: `apps/api/tests/unit/test_lab_pareto_api.py` with TestClient + fakes

```http
GET /api/v1/lab/pareto?hours=24
→ { "formula": "...", "models": [ ModelAggregate... ] }

GET /api/v1/sessions/{session_id}/traces
→ { "traces": [ ... ] }  # session token required
```

- [x] Commit `feat(api): lab pareto and session traces endpoints`

---

### Task 7: Web Pareto panel

**Owned by UX plan:** `docs/superpowers/plans/2026-09-03-lab-observability-ux.md` (Tasks 3–4) + spec `…-lab-observability-ux-design.md`.

**Files (do not fork a second UI):**
- `apps/web/src/components/ModelsFloat.tsx`, `ParetoPanel.tsx`
- Wire `GET /lab/pareto` in `client.ts`; hook into Models float tab «Рейтинг»

- [ ] Ensure API response shape matches `ParetoPanel` props from UX plan
- [ ] No ad-hoc table in Chat — use Models float only
- [ ] Commit with UX work or `feat(web): wire pareto API into ModelsFloat`

---

### Task 8: Integration verification

- [ ] `uv run pytest` for new unit + integration tests
- [ ] Manual: local compose, send chat, open Lab Pareto, see row
- [ ] Commit only if anything left; otherwise stop

## Self-review

- Spec fields covered by Tasks 1–7
- No mid-stream failover change
- Trace save cannot break SSE
- Sibling feedback feature not required for this plan to ship
