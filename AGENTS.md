# Agent instructions (AIChallenge)

## Always

1. Read and follow `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md` for architecture decisions.
2. **Never** read, quote, or commit `.env` or secret values. Use `.env.example` names only.
3. Keep code **domain-agnostic** (no patient/doctor/medical naming in code or default configs).
4. Every assistant answer must attribute **`model_id`** (DB + SSE + UI).
5. **No deploy to the server** (SSH/SCP/Actions Deploy) without an **explicit** user request in that turn. Default: local work and local commits only; push to GitHub only when asked.
6. **Deploy safety:** do not `compose down`, do not bind `:443` / `:8443` from app containers, and do not change the host edge unless the user explicitly asks.

## Project skills (`.cursor/skills/`)

| Skill | When |
|-------|------|
| `aichallenge-architecture` | API modules, layers, SOLID boundaries |
| `aichallenge-secrets` | Env, keys; never read `.env` |
| `aichallenge-llm` | Providers, ModelRouter, SSE model events, probe |
| `aichallenge-docker` | Compose, Dockerfiles, run workflow |
| `aichallenge-frontend` | Chat SPA, session, SSE client |
| `aichallenge-testing` | Tests, FakeLLM, SSE contracts |

## Design review agents (Cursor)

Project subagents in `.cursor/agents/` (format: [Cursor subagents](https://cursor.com/docs/subagents.md)):

| Agent | Role |
|-------|------|
| `designer-visual` | Visual hierarchy |
| `designer-interaction` | Flows / media CTA |
| `designer-density` | Clutter / first paint |
| `designer-a11y` | Accessibility |
| `designer-brand` | Copy / IA |
| `design-lead` | Merge + implement plan |

Slash: `.cursor/commands/design-review.md` (`/design-review`).  
Health check: `scripts/check-design-agents.sh`.

## Stack reminder

- API: FastAPI + uv + Postgres + Alembic
- Web: Vite + React + TypeScript (composer model pin, compare via probe, visitor history sidebar)
- LLM: OpenAI-compatible + failover chain; default provider **RouterAI** (`LLM_BASE_URL` / `ROUTERAI_KEY`)
- Auth: anonymous sessions in v1 (`X-Session-Token` + `X-Visitor-Id`)
- Live: see README Production
