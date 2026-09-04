---
name: aichallenge-docker
description: >-
  Docker Compose, Dockerfiles, and monorepo run workflow for AIChallenge
  (api, web, Postgres). Use when editing compose files, Dockerfiles, nginx
  proxy, migrations on boot, or local/cloud run instructions.
---

# AIChallenge Docker

## Services (v1)

| Service | Role |
|---------|------|
| `db` | Postgres 16, volume, healthcheck |
| `api` | FastAPI; wait for db; Alembic migrate then serve |
| `web` | Vite (dev) or nginx static + `/api` → `api:8000` |

## Practices

- Multi-stage builds; non-root user for api/web runtime images
- API deps via `uv sync --frozen`
- Compose uses `env_file: .env` (gitignored); never bake secrets into images
- Prefer healthchecks over blind `sleep`
- Expose api port publicly only for local debug; prod-like traffic via web proxy

## Common commands (after scaffold exists)

```bash
docker compose up --build
docker compose exec api <migrate-or-shell>
```

Do not invent alternate one-off compose stacks unless asked; extend the root `docker-compose.yml`.

## Prod

- `docker-compose.prod.yml`: web published on loopback only; host nginx terminates TLS on `:8443`.
- Public `:443` is **xray VLESS Reality** with fallthrough to `127.0.0.1:8443` — not Docker.
- Deploy: `scripts/deploy.sh` — runs `assert-edge-safe.sh`, rolling `compose up --build -d` (**no** `down`; **no** casual xray edits).
- Host fuses: `/usr/local/sbin/assert-edge-safe.sh`, `reality-guard.timer` (auto-restart xray if fallthrough dies while nginx lives).
- After deploy verify local Reality fallthrough (`STRICT_HOST=1 ./scripts/assert-edge-safe.sh`) and public `https://aichallenge.arcilite.ru/`.
- See always-on rule `.cursor/rules/deploy-vless-safe.mdc`.
- Public URL notes live in README / `docs/env-local.md` — do not put host IPs in skills.
