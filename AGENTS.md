# Agent instructions (AIChallenge)

## Always

1. Read and follow `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md` for architecture decisions.
2. **Never** read, quote, or commit `.env` or secret values. Use `.env.example` names only.
3. Keep code **domain-agnostic** (no patient/doctor/medical naming in code or default configs).
4. Every assistant answer must attribute **`model_id`** (DB + SSE + UI).
5. **No deploy to the server** (SSH/SCP/Actions Deploy) without an **explicit** user request in that turn. Default: local work and local commits only; push to GitHub only when asked.

## Project skills (`.cursor/skills/`)

| Skill | When |
|-------|------|
| `aichallenge-architecture` | API modules, layers, SOLID boundaries |
| `aichallenge-secrets` | Env, keys; never read `.env` |
| `aichallenge-llm` | Providers, ModelRouter, SSE model events, probe |
| `aichallenge-docker` | Compose, Dockerfiles, run workflow |
| `aichallenge-frontend` | Chat SPA, session, SSE client |
| `aichallenge-testing` | Tests, FakeLLM, SSE contracts |

## Stack reminder

- API: FastAPI + uv + Postgres + Alembic
- Web: Vite + React + TypeScript
- LLM: OpenAI-compatible + failover chain; default provider **RouterAI** (`LLM_BASE_URL` / `ROUTERAI_KEY`)
- Auth: anonymous sessions in v1
