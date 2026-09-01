---
name: aichallenge-frontend
description: >-
  Vite React TypeScript chat SPA conventions for AIChallenge: anonymous
  session, SSE tokens, model_id labels, API client. Use when editing apps/web
  or chat UI/SSE client code.
---

# AIChallenge Frontend

## Stack

Vite + React + TypeScript SPA under `apps/web`.

## Session (v1)

1. On load: reuse `localStorage` session if `GET /sessions/{id}` succeeds; else forget and `POST /sessions`
2. Store `session_id` + `access_token`
3. Send `X-Session-Token` on session-scoped calls
4. On 404 (stale after DB reset): drop stored session and mint a new one — do not leave chat broken

## Chat + SSE

- Prefer streaming from `POST .../messages` (SSE body)
- Handle `model`, `token`, `message_end`, `error`
- Show `model_id` on each assistant message; update on `model` / `message_end`
- Reload history from `GET .../messages` including `model_id`

## Config

- Browser calls relative `/api` behind nginx in Docker
- Optional `VITE_API_URL` for non-proxied local API

## Scope

Functional chat + LLM probe UI in v1. No heavy design system unless asked. Keep domain-agnostic copy (no medical role wording).
