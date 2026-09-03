# Feedback → Dataset → Router Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.


> ⚠️ **Read first:** [Prep decisions](./2026-09-03-observability-prep-decisions.md) — locked technical contract from a code-reading pass.
> Where this plan and that file disagree, **the prep decisions win**.

**Goal:** Thumbs on assistant messages, preference export for offline/DS use, and soft router bias from down-vote rates.

**Architecture:** New `MessageFeedback` entity + repo; `POST /messages/{id}/feedback`; Lab stats + JSONL export; ModelRouter consults a `FeedbackPenaltyStore` (in-process TTL map refreshed from DB aggregates on a timer or on each request with cache). Requires **Pareto Lab / RunTrace** shipped first so export rows can join traces.

**Tech Stack:** Same as API/web stack; no new ML libraries in v1.

**Spec:** `docs/superpowers/specs/2026-09-03-feedback-router-design.md`  
**Prerequisite plan:** `docs/superpowers/plans/2026-09-03-model-pareto-lab.md`

## Global Constraints

- Domain-agnostic UI copy (“Helpful” / “Not helpful”)
- `model_id` required on assistant messages used for stats
- Failover still pre-first-token only; bias only reorders/skips candidates **before** streaming
- FakeLLM in CI; never commit secrets
- Hexagonal layering; no deploy without explicit ask
- Export must not log full prompts unless `FEEDBACK_EXPORT_INCLUDE_CONTENT=true`

## File map

| Path | Responsibility |
|------|----------------|
| `apps/api/src/app/domain/feedback.py` | `MessageFeedback`, `ModelFeedbackStats`, `PreferenceRow` |
| `apps/api/src/app/domain/ports.py` | `FeedbackRepository` |
| `apps/api/src/app/application/feedback.py` | Submit + export builders |
| `apps/api/src/app/adapters/persistence/models.py` | `MessageFeedbackRow` |
| `apps/api/src/app/adapters/persistence/feedback_repo.py` | Repo |
| `apps/api/alembic/versions/00Y_message_feedback.py` | Migration |
| `apps/api/src/app/adapters/api/feedback.py` | POST feedback |
| `apps/api/src/app/adapters/api/lab.py` | stats + export |
| `apps/api/src/app/adapters/llm/router.py` | apply penalties in `_candidates` |
| `apps/api/src/app/adapters/llm/feedback_penalties.py` | threshold math + cache |
| `apps/web/src/components/Turn.tsx` (or bubble) | thumbs UI |
| `apps/web/src/api/client.ts` | `postFeedback` |
| Tests under `apps/api/tests/unit/` + one API test |

---

### Task 1: Domain + port

**Files:**
- Create: `apps/api/src/app/domain/feedback.py`
- Modify: `apps/api/src/app/domain/ports.py`
- Test: `apps/api/tests/unit/test_feedback_entities.py`

```python
@dataclass
class MessageFeedback:
    id: UUID
    message_id: UUID
    session_id: UUID
    visitor_hash: str | None
    value: Literal["up", "down"]
    created_at: datetime

@dataclass(frozen=True)
class ModelFeedbackStats:
    model_id: str
    ups: int
    downs: int

    @property
    def down_rate(self) -> float:
        n = self.ups + self.downs
        return 0.0 if n == 0 else self.downs / n
```

- [x] Tests + commit `feat(domain): message feedback entities`

---

### Task 2: Penalty eligibility pure function

**Files:**
- Create: `apps/api/src/app/adapters/llm/feedback_penalties.py`
- Test: `apps/api/tests/unit/test_feedback_penalties.py`

```python
def should_penalize(stats: ModelFeedbackStats, *, min_votes: int, down_rate_threshold: float) -> bool:
    n = stats.ups + stats.downs
    if n < min_votes:
        return False
    return stats.down_rate >= down_rate_threshold
```

- [x] Table-driven tests (0 votes, 4 downs of 4, 3/10, etc.)
- [x] Commit `feat(llm): feedback penalty predicate`

---

### Task 3: DB + repository

**Files:**
- `MessageFeedbackRow` — unique on `message_id`
- Alembic migration
- `SqlAlchemyFeedbackRepository.upsert`, `stats_by_model(since)`, `export_rows` joining `messages.model_id` + optional `run_traces`

- [x] Commit `feat(db): message_feedback table`

---

### Task 4: SubmitFeedback use-case + API

**Files:**
- `apps/api/src/app/application/feedback.py`
- `apps/api/src/app/adapters/api/feedback.py`
- Tests: wrong session → 404/403; non-assistant → 400; upsert flips value

```http
POST /api/v1/messages/{message_id}/feedback
Headers: X-Session-Token, X-Visitor-Id
Body: {"value":"up"}
→ 200 {"message_id","value"}
```

- [x] Commit `feat(api): message feedback endpoint`

---

### Task 5: Wire penalties into ModelRouter

**Files:**
- Modify: `router.py` `_candidates`
- `deps.py`: load stats since `now-7d`, build `set[str]` penalized models, inject callable `is_penalized(model_id) -> bool`
- Penalized models: skip in auto mode **unless** explicitly pinned as `preferred_model`
- Cache stats 60s in process to avoid DB hit every token request

- [x] Unit test with FakeLLM two-model chain: penalize first → second used
- [x] Commit `feat(llm): soft-penalize models from feedback rates`

---

### Task 6: Lab stats + JSONL export

**Files:**
- Extend lab router:

```http
GET /api/v1/lab/feedback-stats?hours=168
GET /api/v1/lab/preference-export?hours=168
Content-Type: application/x-ndjson
```

Each line = `PreferenceRow` dict; include trace attempts when present; content only if settings flag true.

- [x] Commit `feat(api): feedback stats and preference export`

---

### Task 7: Web thumbs + lab table

**Owned by UX plan:** `docs/superpowers/plans/2026-09-03-lab-observability-ux.md` (Tasks 5–6) + microcopy in `…-lab-observability-ux-checklist.md`.

**Files (do not fork a second UI):**
- `FeedbackStrip.tsx` on `Turn`, `FeedbackStatsPanel.tsx` in Models float tab «Оценки»

- [ ] API fields include optional `penalized` for chip «Ниже в очереди»
- [ ] Commit with UX work or `feat(web): wire feedback API into FeedbackStrip`

---

### Task 8: Verification + ops note

- [x] Full pytest for new modules
- [x] Document in `docs/env-local.md` **names only**: `FEEDBACK_DOWN_RATE_THRESHOLD`, `FEEDBACK_MIN_VOTES`, `FEEDBACK_PENALTY_TTL_SECONDS`, `FEEDBACK_EXPORT_INCLUDE_CONTENT`
- [x] Add matching empty placeholders to `.env.example`
- [x] Commit `docs: feedback router env knobs`

## Self-review

- Prerequisite RunTrace used in export join (graceful if missing attempts)
- Pin still overrides penalty
- One vote per message
- No training loop in-repo — export is the DS handoff to Kalinin/SkyNet

## Resume order

1. Finish Pareto Lab plan completely  
2. Execute this plan task-by-task  
3. Optional later: offline ranker → load weight file (new spec)
