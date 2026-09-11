# Context Strategies (Day 10) Implementation Plan

> **For agentic workers:** Execute task-by-task. Spec: `docs/superpowers/specs/2026-09-11-context-strategies-design.md`

**Goal:** Mutually exclusive `context_mode` (none|compress|sliding|facts) via modular `assemble_context`, plus dialog fork for branching; agent workshop UI + challenge 10.

**Architecture:** Domain `context_strategies/` consumed by `run_agent_with_dialog`; Day-9 compress becomes one mode; fork creates new dialog with message prefix.

**Tech Stack:** FastAPI, SQLAlchemy/Alembic, React/TS, FakeLLM tests

**Spec:** `docs/superpowers/specs/2026-09-11-context-strategies-design.md`

## Global Constraints

- Domain-agnostic naming; no medical terms
- Every assistant reply exposes `model_id`
- No secrets in repo; FakeLLM in CI
- Day-9 compress behavior preserved as `mode=compress`
- Mutually exclusive modes; `none` = no strategy effects

## Files

| Path | Role |
|------|------|
| `apps/api/src/app/domain/context_strategies/*` | assemble + modes |
| `apps/api/alembic/versions/009_*.py` | facts + branch columns |
| `apps/api/src/app/application/agent_run.py` | wire modes + facts extract |
| `apps/api/src/app/application/dialog_fork.py` | fork use case |
| `apps/api/src/app/adapters/api/*` | schemas, endpoints |
| `apps/web/src/**` | selector, facts panel, fork UI |
| `challenges/10-context-strategies/` | compare + video |

---

### Task 1: Domain assemble_context

Create package with types, sliding, facts helpers, compress adapter, `assemble_context`.

### Task 2: Persistence 009

Add `facts`, `parent_dialog_id`, `branch_label`, `forked_from_message_id` to domain/ORM/repo; clear resets facts.

### Task 3: Application + API

`context_mode` on run; facts LLM extract; fork endpoint; response `context_strategy`.

### Task 4: Web

Replace compress checkbox with mode selector; facts panel; checkpoint fork + branch switch.

### Task 5: Challenge 10

`run.py`, README, record.mjs `RECORD_ONLY=10`.
