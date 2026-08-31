# CLAUDE.md — Claude Code entrypoint (AIChallenge)

You are implementing / maintaining this repo in **Claude Code** (Anthropic). Cursor IDE may also open the repo; do not assume Cursor Cloud.

## Read first

1. `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md`
2. `docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md` (implementation plan)
3. `AGENTS.md`

## Secrets (critical)

- **Never** read, print, or commit `.env` or secret values.
- Human creates `.env` from `.env.example` outside the chat.
- Discuss variable **names** only (`LLM_API_KEY`, `DATABASE_URL`, …).
- If a key is missing: use `USE_FAKE_LLM=true` / `FakeLLMProvider` for tests and demos.

## Deploy

- Do **not** SSH/SCP or run production deploy unless the human **explicitly** asks.
- Default: local commits only; push to GitHub only when asked.

## Project skills

Same conventions live in `.cursor/skills/aichallenge-*` (architecture, secrets, llm, docker, frontend, testing). Apply them when touching those areas.

## Stack (v1)

- `apps/api` — FastAPI hexagonal modular monolith (`uv`, Postgres, SSE)
- `apps/web` — Vite + React + TypeScript
- Docker Compose: `db`, `api`, `web`
- Every assistant reply exposes resolved `model_id`
- Domain-agnostic naming only (no patient/doctor in code or default configs)

## When asked to build v1

Execute the Claude Code plan task-by-task, checkbox + commit per task.
