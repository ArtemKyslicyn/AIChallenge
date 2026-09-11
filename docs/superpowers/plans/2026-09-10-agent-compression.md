# Agent Context Compression (Day 9) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** LLM rolling summary + recent-N window for agent dialogs; UI toggle; Challenge 09 video.

**Architecture:** Domain `compress_history` pure helpers; application refreshes summary via ChatRouter then `run_agent` with synthetic history; Alembic 008 adds summary columns; web toggle + meter.

**Tech Stack:** FastAPI, Alembic, React, FakeLLM tests, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-10-agent-compression-design.md`

## Global Constraints

- Domain-agnostic; FakeLLM in CI; `model_id` on answers; no secrets

---

### Task 1: Domain + migration + run_agent wire

- [ ] `token_meter` / new `context_compress.py` helpers + tests
- [ ] Alembic `008_agent_dialog_summary.py`
- [ ] `run_agent_with_dialog` compress path + API schema
- [ ] Unit tests FakeLLM (summary call + main call)

### Task 2: Web UI

- [ ] Toggle + summary panel + compression stats on meter
- [ ] Pass `compress` / knobs in `runAgentWorkshop`

### Task 3: Challenge 09 + record

- [ ] `challenges/09-compression/` run.py + README
- [ ] `RECORD_ONLY=09` Playwright
- [ ] Deploy + video

---
