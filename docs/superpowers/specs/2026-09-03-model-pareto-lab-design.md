# Model Pareto Lab — Design Spec

**Date:** 2026-09-03  
**Status:** Deferred (plan ready; implement when resumed)  
**Depends on:** v1 chat SSE + ModelRouter + existing Lab UI floats  
**Sibling:** `2026-09-03-feedback-router-design.md` (consumes the same `run_trace`)

## Goal

Make every assistant completion measurable and comparable: persist a **run trace**, expose aggregates, and show a **Pareto / ranking** view (quality proxy × latency × cost proxy × reliability) — same mental model as Kalinin `ranked_pipelines_by_value`, applied to LLM routing.

## Non-goals (v1 of this feature)

- No GPU training, LoRA, or external MLflow
- No change to mid-stream failover rules (still pre-first-token only)
- No raw IP / secrets / full prompt dumps in public API by default
- No mandatory thumbs (that is the sibling feature)

## Domain

### `RunTrace` (new)

| Field | Notes |
|-------|--------|
| `id` | UUID |
| `session_id`, `message_id` | FK to session + assistant message |
| `visitor_hash` | nullable copy from session (analytics, not PII) |
| `preferred_model` | pin or `auto` |
| `resolved_model_id` | required when answer persisted |
| `attempts` | JSON list: `{model_id, ok, reason, ttft_ms?, error_kind?}` |
| `ttft_ms`, `total_ms` | timings |
| `token_count_est` | optional; chars/4 or provider usage if available |
| `cost_proxy` | optional float; heuristic by model tier (config table) |
| `tool_rounds` | int |
| `tool_ok` | bool \| null |
| `status` | `ok` \| `error` \| `aborted` \| `exhausted` |
| `created_at` | timestamptz |

### Aggregates (read model, not a table)

Per `model_id` over a window: `n`, `success_rate`, `p50_ttft_ms`, `p50_total_ms`, `avg_cost_proxy`, `failover_victim_rate` (how often this model was tried and failed).

**Pareto axes (v1):** X = `p50_total_ms` (lower better), Y = `success_rate` (higher better), size or color = `avg_cost_proxy`. Ranking score for table:  
`score = success_rate / max(p50_total_ms_s, 0.2) / max(avg_cost_proxy, 0.01)`  
(document formula in UI; tune later).

## Ports

```text
RunTraceRepository.save(trace) -> None
RunTraceRepository.list_for_session(session_id) -> list[RunTrace]
RunTraceRepository.aggregate(since, until) -> list[ModelAggregate]
```

Application: after chat stream finalizes (ok / abort / error / exhausted), build and save trace. Router should expose attempt history for the request (extend without breaking stream contract).

## HTTP API

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/api/v1/lab/pareto?hours=24` | session token (same as other lab) | aggregates + formula metadata |
| `GET` | `/api/v1/sessions/{id}/traces` | session owner | traces for one chat (debug) |

Optional SSE: do **not** stream full attempts by default; keep bubble quiet. Lab float reads REST.

## UI

- New section or tab inside existing Lab / Debug float: **Pareto**
- Scatter or ranked table (table-first for v1; scatter optional)
- Link “why this model” → last N attempts for current session

## Config

- `RUN_TRACE_ENABLED=true` (default on in prod after ship)
- `MODEL_COST_PROXY_JSON` optional map `model_id -> float` in settings / env (no secrets)

## Testing

- Unit: trace builder from fake router attempts; aggregate math
- Integration: one SSE chat → row in `run_traces`
- FakeLLM only in CI

## Privacy

- Store `visitor_hash` only (already hashed)
- Do not store full user prompt in `run_traces` v1 (join messages if needed server-side for admin export later)
