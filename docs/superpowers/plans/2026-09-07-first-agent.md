# First Agent (Day 6) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Day-6 agent workshop: `AgentDefinition` + `run_agent` API and a shell workspace `Чат | Агенты` where users configure an agent and run stateless probes that return only `{content, model_id}`.

**Architecture:** Domain holds pure `AgentDefinition` + validation. Application `run_agent` assembles `[SYSTEM, USER]` and calls `ChatRouter.complete_chat` (sibling to `complete_probe`). HTTP `POST /api/v1/agent-workshop/run` with kill switch, size limits, visitor rate cap. Web: App shell mode; `AgentWorkshop` without chat chrome. Challenge 06 hits the new endpoint.

**Tech Stack:** FastAPI + uv, Vite React TS, localStorage drafts, FakeLLM/ChatRouter in tests

**Spec:** `docs/superpowers/specs/2026-09-07-first-agent-design.md`

## Global Constraints

- Code names: `AgentDefinition`, `run_agent`, `agent_workshop` — no bare type `Agent`
- UI RU: «Агенты», «Инструкция агента»; domain-agnostic
- Errors: 422 / 502 / 503 / 404 (disabled) — shared `{error:{code,message}}`
- Auth: no session required; send `X-Visitor-Id`
- Stateless runs only; no Session/Message/RunTrace for agent runs
- Never call `/llm/complete` from Agents UI
- No secrets in commits; FakeLLM in CI
- Models float unchanged

## File map

| Path | Role |
|------|------|
| `apps/api/src/app/domain/agent_definition.py` | `AgentDefinition` + `validate_agent_definition` |
| `apps/api/src/app/application/agent_run.py` | `run_agent` |
| `apps/api/src/app/adapters/api/agent_workshop.py` | HTTP router |
| `apps/api/src/app/adapters/api/schemas.py` | request/response DTOs |
| `apps/api/src/app/core/settings.py` | `agents_run_enabled`, optional rate |
| `apps/api/src/app/main.py` | include router |
| `.env.example`, `docs/env-local.md` | `AGENTS_RUN_ENABLED` |
| `apps/web/src/App.tsx` | shell mode, conditional chrome |
| `apps/web/src/shellMode.ts` | persist + `?shell=agents` |
| `apps/web/src/agents/*` | drafts, presets, API client, workshop UI |
| `apps/web/src/index.css` | workshop layout |
| `challenges/06-first-agent/*` | README, prompt, run.py |
| `challenges/_lib/prod_client.py` | `agent_run()` |
| `challenges/record/*` | challenge-06 recording |
| `challenges/README.md` | list Day 6 |

---

### Task 1: Domain `AgentDefinition` + unit tests

**Files:**
- Create: `apps/api/src/app/domain/agent_definition.py`
- Test: `apps/api/tests/unit/test_agent_definition.py`

**Produces:** `AgentDefinition`, `validate_agent_definition(def, *, message, max_chars) -> None` raising `MessageValidationError`

- [ ] **Step 1:** Failing tests for empty system_prompt/message, oversize, happy path
- [ ] **Step 2:** Implement dataclass + validate (no ChatRouter imports)
- [ ] **Step 3:** `uv run pytest apps/api/tests/unit/test_agent_definition.py -q` PASS

---

### Task 2: `run_agent` use case + Fake router tests

**Files:**
- Create: `apps/api/src/app/application/agent_run.py`
- Test: `apps/api/tests/unit/test_agent_run.py`

**Produces:**

```python
async def run_agent(
    *,
    definition: AgentDefinition,
    message: str,
    router: ChatRouter,
    enabled: bool,
    max_message_chars: int,
    generation: GenerationParams | None = None,
) -> CompletionResult
```

- Raises `ProbeDisabledError` if not enabled (reuse)
- Validates via domain helper
- Builds SYSTEM + USER; `complete_chat` with `preferred_model` + generation

- [ ] **Step 1:** Test enabled path returns content+model_id; disabled raises; generation forwarded
- [ ] **Step 2:** Implement
- [ ] **Step 3:** pytest PASS

---

### Task 3: HTTP `POST /agent-workshop/run` + settings + analytics

**Files:**
- Modify: `settings.py` (`agents_run_enabled: bool = True`), schemas, `main.py`, `.env.example`, `docs/env-local.md`
- Create: `adapters/api/agent_workshop.py`
- Optional: simple in-memory visitor rate limiter in application or adapter (hourly cap, e.g. 60)
- Test: extend `test_api_routes.py` or `tests/unit/test_agent_workshop_api.py`

**Produces:** endpoint returning `{content, model_id}`; 422/404/503 shapes; fail-open analytics events

- [ ] **Step 1:** API tests happy + empty → 422 + disabled → 404
- [ ] **Step 2:** Wire router + settings
- [ ] **Step 3:** pytest PASS

---

### Task 4: Web shell mode + AgentWorkshop

**Files:**
- Create: `shellMode.ts`, `agents/drafts.ts`, `agents/presets.ts`, `agents/api.ts`, `components/AgentWorkshop.tsx` (+ small subcomponents if needed)
- Modify: `App.tsx`, `Chat.tsx` empty-state link, `index.css`, `api/client.ts` if needed for shared `request`

**Behavior:**
- `chat | agents` in topbar; agents: no sidebar / Новый чат / float
- Agents renders without session
- Desktop split; mobile sheet for settings
- Stateless run log; Stop; draft lifecycle per spec

- [ ] **Step 1:** shellMode helpers + App wiring
- [ ] **Step 2:** Workshop UI + CSS
- [ ] **Step 3:** Manual smoke / `npm run build`

---

### Task 5: Challenge 06 + record

**Files:**
- Create: `challenges/06-first-agent/{README,prompt.txt,run.py}`
- Modify: `prod_client.py`, `challenges/README.md`, `challenges/record/record.mjs`

- [ ] **Step 1:** `agent_run()` helper
- [ ] **Step 2:** run.py + README
- [ ] **Step 3:** record path for challenge-06 (selectors for shell + workshop)

---

### Task 6: Spec status + verify

- [ ] Mark design spec Status: Implemented (v1)
- [ ] Run api unit tests for agent_* + web build
- [ ] Commit only if user asks

## Self-review checklist

- [x] Spec coverage: domain, run, API, shell UX, limits, challenge
- [x] No graph freeze / no server YAML presets
- [x] Naming matches spec (`agent-workshop`)
