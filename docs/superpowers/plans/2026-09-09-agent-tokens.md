# Agent Token Meter (Day 8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Approximate token metering + history truncation for agent workshop, with UI meter and Challenge 08 demo/video.

**Architecture:** Pure domain helpers (`estimate_tokens`, `fit_messages_to_budget`) used by `run_agent`; API returns `tokens` + `truncation` + `cost_proxy`; web shows meter/banner; challenge forces low `context_limit`.

**Tech Stack:** FastAPI, domain pure Python, React AgentWorkshop, Playwright record, FakeLLM tests.

**Spec:** `docs/superpowers/specs/2026-09-09-agent-tokens-design.md`

## Global Constraints

- Domain-agnostic naming; no secrets in chat/commits
- FakeLLM in unit tests; no real keys in CI
- `model_id` still required on every assistant answer
- Approx `len//4` only (no tiktoken)

---

### Task 1: Domain token helpers + unit tests

**Files:**
- Create: `apps/api/src/app/domain/token_meter.py`
- Create: `apps/api/tests/unit/test_token_meter.py`

- [ ] Test estimate / fit (short fits, long drops oldest, system+latest user kept)
- [ ] Implement helpers
- [ ] Tests green

### Task 2: Wire into `run_agent` + API schema

**Files:**
- Modify: `apps/api/src/app/application/agent_run.py`
- Modify: `apps/api/src/app/adapters/api/schemas.py`
- Modify: `apps/api/src/app/adapters/api/agent_workshop.py`
- Modify: `apps/api/tests/unit/test_agent_run.py`
- Modify: `challenges/_lib/prod_client.py` (optional fields)

- [ ] `run_agent` returns usage metadata (or side result object)
- [ ] Response includes tokens/truncation/cost_proxy; accept optional `context_limit`
- [ ] Unit tests for truncate path with FakeLLM

### Task 3: Web meter UI

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/components/AgentWorkshop.tsx`
- Modify: CSS if needed (`apps/web/src` styles)

- [ ] Show token strip + truncation banner on solo replies

### Task 4: Challenge 08 + record script

**Files:**
- Create: `challenges/08-tokens/`
- Modify: `challenges/record/record.mjs`, `challenges/README.md`

- [ ] `run.py` short / long / overflow cases
- [ ] Playwright scenario with pauses
- [ ] Record `challenge-08.mp4` against prod after deploy (or local)

---
