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
2. Store chats in `aichallenge.session_store` (v2: `visitorId` + `access_token` per chat)
3. Send `X-Session-Token` on session-scoped calls; send `X-Visitor-Id` on all calls
4. On 404 (stale after DB reset): drop stored session and mint a new one — do not leave chat broken
5. **History sidebar = local cache only.** List sessions that have a token in this browser; merge server titles only for those ids. Wipe store if `visitorId` mismatches. Reject `listMessages`/SSE if session not in local store.
6. JSON `fetch` uses a request timeout (default ~30s; probe longer) so boot cannot spin forever on a hung network.
7. Load `listMessages` only when `session` changes — not when parent re-creates callbacks (compare turns are in-memory only and would otherwise vanish after `refreshHistory`).

## Chat + SSE

- Prefer streaming from `POST .../messages` (SSE body); optional `model` pin from the composer
- Handle `model`, `token`, `message_end`, `error`
- Show `model_id` on each assistant message; update on `model` / `message_end`
- Reload history from `GET .../messages` including `model_id`
- **Compare mode** (“Два рядом”): two `POST /llm/complete` probes rendered side-by-side in the thread; **not** persisted as chat rows

## Config

- Browser calls relative `/api` behind nginx in Docker
- Optional `VITE_API_URL` for non-proxied local API
- Prod tip: if HTTPS `:443` stalls, use the documented `:8443` URL (README)

## Scope

Functional chat + generation controls + compare + history sidebar. No heavy design system unless asked. Keep domain-agnostic copy (no medical role wording).
