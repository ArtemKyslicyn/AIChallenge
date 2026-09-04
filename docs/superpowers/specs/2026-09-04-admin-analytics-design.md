# Admin Analytics (Event Store + Multi-Product Console) — Design Spec

**Date:** 2026-09-04  
**Status:** Draft — awaiting review (revised: private multi-product repo)  
**Depends on:** AIChallenge v1 chat + traces/feedback as **one product source**  
**Decision locked:** Option **A** — own Postgres event-store + admin UI (PostHog-*like* capture, not self-hosted PostHog)

## 1. Goal

Private **ops / product console** for a small trusted circle:

- multi-**product** dashboard (AIChallenge is the first product; more later)
- uniques, visits, requests, funnels, model/ops graphs
- durable append-only **event store**

Public AIChallenge chat stays anonymous. Console is **not** inside the chat SPA and **not** in the public AIChallenge git history as an implementation plan.

## 2. Non-goals (v1)

- No self-hosted PostHog / ClickHouse / Kafka
- No session replay / marketing pixels
- No fine-grained RBAC (one admin role)
- No secrets / LLM keys in the UI
- No default storage of full prompts/completions
- No admin UI inside `apps/web`
- Implementation **plan** must not be committed to the public AIChallenge repo

## 3. Decisions (locked)

| Topic | Choice |
|-------|--------|
| Repository | **Separate private GitHub repo** (ops console + event API) |
| Products | First-class `product_id` (e.g. `aichallenge`, later others) |
| AIChallenge role | **Producer** of events (HTTP capture / thin emit), not host of the admin app |
| Placement | Subdomain e.g. `ops.<domain>` or `admin.<domain>` |
| Audience | Narrow circle (1–3 people) |
| Analytics engine | Own Postgres event store + SQL aggregates |
| Capture shape | PostHog-like `capture` (`event`, `distinct_id`, `properties`, `timestamp`, `product_id`) |
| Auth | Dedicated admin session; not chat `X-Visitor-Id` |
| Network | VPN / IP allowlist + app login |
| Plans / internal docs | Keep **out of public git**; live in the private repo or local-only notes |

## 4. Domain

### 4.1 `AnalyticsEvent` (append-only)

| Field | Notes |
|-------|--------|
| `id` | UUID |
| `product_id` | string, indexed — tenant-light product key |
| `created_at` | server receive time |
| `event_time` | client/event time |
| `name` | e.g. `assistant_completed` |
| `distinct_id` | usually visitor hash |
| `session_id` | opaque string/UUID nullable |
| `message_id` | nullable |
| `props` | JSONB |
| `source` | `api` \| `web` \| `admin` \| `system` |

Indexes: `(product_id, event_time DESC)`, `(product_id, name, event_time DESC)`, `(product_id, distinct_id, event_time DESC)`.

### 4.2 Product registry (v1 minimal)

| Field | Notes |
|-------|--------|
| `id` | slug (`aichallenge`) |
| `title` | display name |
| `created_at` | |

Dashboard always scoped by selected `product_id` (switcher in header).

### 4.3 Events for product `aichallenge` (v1)

Same catalog as before: `app_opened`, `message_sent`, `assistant_completed`, `assistant_failed`, `feedback_set`, studio completions, `admin_login` / `admin_logout`.  
Other products define their own event names; store stays generic.

## 5. Architecture (private repo)

```text
private-repo/
  apps/api      — capture + admin auth + aggregates
  apps/web      — multi-product dashboard
  docs/         — specs & plans (private only)
```

AIChallenge monorepo later adds only a **small emitter** (env: capture URL + ingest key + `product_id=aichallenge`). No admin SPA in AIChallenge.

## 6. HTTP (console API)

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `POST` | `/v1/capture` | ingest key | product beacons / server emits |
| `POST` | `/v1/admin/login` | rate-limited | admin session |
| `GET` | `/v1/admin/overview?product_id=&hours=` | admin | KPIs |
| `GET` | `/v1/admin/timeseries` | admin | graphs |
| `GET` | `/v1/admin/funnel` | admin | funnel |
| `GET` | `/v1/admin/events` | admin | explore |
| `GET` | `/v1/admin/products` | admin | product switcher |

## 7. Admin UI

- Login  
- Product switcher  
- Overview / Usage / Funnel / Explore for the **selected** product  
- No cross-product PII join beyond `product_id`

## 8. AIChallenge integration (later, thin)

- Env names only: `ANALYTICS_CAPTURE_URL`, `ANALYTICS_INGEST_KEY`, `ANALYTICS_PRODUCT_ID`  
- Emit on complete / feedback / optional `app_opened`  
- Fail-open: analytics errors must not break chat  

## 9. Success criteria

- Private repo runs console + capture for `product_id=aichallenge`  
- Second product can be registered without schema redesign  
- Public AIChallenge repo has no implementation plan for this console  
- Chat UX unchanged until thin emitter is explicitly added  

## 10. Open points

- Private repo name / GitHub org  
- Whether AIChallenge emitter ships in the same milestone as console MVP  
- Cookie domain for `ops.` vs API host  
