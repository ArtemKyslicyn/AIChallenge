# Feedback → Dataset → Router — Design Spec

**Date:** 2026-09-03  
**Status:** Deferred (plan ready; implement when resumed)  
**Depends on:** `2026-09-03-model-pareto-lab-design.md` (`RunTrace` + aggregates)  
**Kalinin analogue:** closed-loop QC / preference signal → pipeline ranking

## Goal

Collect explicit thumbs on assistant messages, persist a **preference dataset**, and use aggregates to **bias routing** (exhaust / deprioritize models with bad feedback; optionally boost good ones) without mid-stream model splicing.

## Non-goals

- No RLHF / reward-model training on this VPS in v1
- No changing answers after the fact
- No public dump of full chats without auth (export is ops-only / local script)
- No per-visitor shadow profiles beyond existing `visitor_hash`

## Domain

### `MessageFeedback`

| Field | Notes |
|-------|--------|
| `id` | UUID |
| `message_id` | assistant message only; unique per visitor or per message (one vote wins) |
| `session_id` | denormalized |
| `visitor_hash` | nullable |
| `value` | `up` \| `down` |
| `created_at` | timestamptz |

One feedback per `(message_id)` in v1 (last write wins) to keep UX simple.

### Preference export row (derived)

JSONL line for offline / Kalinin train factory:

```json
{
  "message_id": "...",
  "model_id": "...",
  "feedback": "up",
  "ttft_ms": 1200,
  "total_ms": 4500,
  "attempts": [],
  "created_at": "..."
}
```

Prompt text optional behind `FEEDBACK_EXPORT_INCLUDE_CONTENT=false` default.

### Router bias (v1)

In-process (same as exhausted TTL) **soft penalties**:

- If `down` rate for `model_id` over last N votes ≥ threshold → treat as temporarily exhausted / move to end of candidate list for TTL
- Config: `FEEDBACK_DOWN_RATE_THRESHOLD=0.6`, `FEEDBACK_MIN_VOTES=5`, `FEEDBACK_PENALTY_TTL_SECONDS=86400`

Does **not** replace provider failover; stacks with it. Pin (`preferred_model`) still tried first.

Later (out of scope): export → train ranker → load weights file.

## Ports

```text
FeedbackRepository.upsert(message_id, session_id, visitor_hash, value) -> MessageFeedback
FeedbackRepository.stats_by_model(since) -> list[ModelFeedbackStats]
FeedbackRepository.export_rows(since, until) -> AsyncIterator[PreferenceRow]
```

Application: `SubmitFeedback` use case validates assistant message ownership via session token.

## HTTP API

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/messages/{id}/feedback` | body `{ "value": "up" \| "down" }` |
| `GET` | `/api/v1/lab/feedback-stats?hours=168` | per-model up/down for lab |
| `GET` | `/api/v1/lab/preference-export?hours=168` | JSONL download (gate: same session auth as lab; rate-limit) |

## UI

- Thumbs under assistant bubble (after `message_end`)
- Optimistic toggle; show selected state
- Lab: small table “feedback by model” next to Pareto

## Testing

- Unit: upsert + penalty eligibility math
- API: cannot feedback another session’s message
- Router: FakeLLM chain order changes when model penalized
- FakeLLM only in CI

## Privacy / product

- Domain-agnostic copy (“Helpful” / “Not helpful”), not medical
- Export endpoint must not appear in public README as open data dump
