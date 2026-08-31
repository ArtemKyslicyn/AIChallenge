# AIChallenge — AI Chat Platform

Domain-agnostic AI chat platform: FastAPI hexagonal modular monolith + Vite/React SPA + Postgres,
with SSE token streaming and visible `model_id` attribution on every assistant reply.

- **Design spec:** `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md`
- **Implementation plan:** `docs/superpowers/plans/2026-08-31-ai-chat-platform-claude-code.md`
- **Agent conventions:** `CLAUDE.md`, `AGENTS.md`

> Status: v1 in progress. This README is expanded in the final task of the plan.

## Local API (no Docker, no provider key)

```bash
cd apps/api
uv sync
uv run pytest tests/unit -v
uv run uvicorn app.main:app --reload --port 8000
curl -s http://localhost:8000/api/v1/health
```

## Secrets

Copy the template and fill it in **your editor**, never in an agent chat:

```bash
cp .env.example .env
```

`.env` is gitignored and must never be read, printed, or committed. Set `USE_FAKE_LLM=true` to run the
whole stack without a provider key.
