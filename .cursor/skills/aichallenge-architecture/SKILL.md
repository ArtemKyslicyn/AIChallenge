---
name: aichallenge-architecture
description: >-
  Enforces Clean/Hexagonal modular monolith layout for the AIChallenge
  monorepo (domain, application, adapters). Use when adding API features,
  modules, repositories, use cases, or refactoring apps/api Python code.
---

# AIChallenge Architecture

Canonical design: `docs/superpowers/specs/2026-08-31-ai-chat-platform-design.md`

## Layout

- `apps/api` — FastAPI modular monolith (`uv`, SQLAlchemy 2, Alembic)
- `apps/web` — Vite + React + TypeScript SPA
- `configs/scenarios` — YAML scenarios (generic language only)

## Layer rules

| Layer | May depend on | Must not |
|-------|---------------|----------|
| `domain` | stdlib / pure types | FastAPI, SQLAlchemy, httpx, env I/O |
| `application` | `domain` ports/entities | frameworks, HTTP details |
| `adapters` | application + domain | leak framework types into domain |
| `core` | wiring/settings/DI | business rules |

## Naming (domain-agnostic)

Use: `Session`, `Message`, `Scenario`, `Participant`, `model_id`.  
Do **not** use product/medical role names in code, API paths, or default configs (`patient`, `doctor`, clinic-specific terms).

## When adding a feature

1. Port in `domain` (Protocol / ABC)
2. Use case in `application`
3. Adapter(s) under `adapters/`
4. Wire in `core` DI
5. Tests with fakes at the port boundary

## Microservices

Stay modular monolith until an explicit decision to split. Prefer extracting an adapter, not a new deployable.
