# Lab Observability UI/UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.


> ⚠️ **Read first:** [Prep decisions](./2026-09-03-observability-prep-decisions.md) — locked technical contract from a code-reading pass.
> Where this plan and that file disagree, **the prep decisions win**.

**Goal:** Качественно спроектировать и внедрить UI/UX для Pareto Lab и Feedback так, чтобы метрики и оценки выглядели продуктово, а не «прикрученной админкой».

**Architecture:** Один новый float «Модели» в `float-dock` (mutex с Debug/Results); feedback strip в assistant `Turn`; вкладки Рейтинг / Оценки; переиспользование CSS-паттернов LabResults/Debug.

**Tech Stack:** React + TS (`apps/web`), existing `index.css` float tokens; API from Pareto + Feedback plans.

**Spec:** `docs/superpowers/specs/2026-09-03-lab-observability-ux-design.md`

## Global Constraints

- Domain-agnostic RU copy only
- Preserve `model_id` visibility on assistant turns
- Match existing float-dock mutex (only one expanded panel)
- No purple/glow AI-slop theme; reuse current accent
- Mobile: 44px targets; Escape + focus return
- Do not block chat if Lab API fails
- Coordinate with: `2026-09-03-model-pareto-lab.md` (Task 7) and `2026-09-03-feedback-router.md` (Task 7) — **this plan owns UX quality**; those tasks should defer to components created here or be replaced by this plan’s UI tasks when executing

## File map

| Path | Responsibility |
|------|----------------|
| `apps/web/src/components/ModelsFloat.tsx` | FAB + panel shell + tabs + mutex props |
| `apps/web/src/components/ParetoPanel.tsx` | Ranking table + empty/loading/error |
| `apps/web/src/components/FeedbackStatsPanel.tsx` | Thumbs aggregates table |
| `apps/web/src/components/FeedbackStrip.tsx` | Per-message useful / not useful |
| `apps/web/src/components/Turn.tsx` | Mount FeedbackStrip |
| `apps/web/src/components/Chat.tsx` | float-dock mutex (Debug \| Results \| Models) |
| `apps/web/src/api/client.ts` | `fetchPareto`, `fetchFeedbackStats`, `postFeedback` |
| `apps/web/src/index.css` | `.models-float-*`, `.feedback-strip-*` |
| `docs/superpowers/specs/2026-09-03-lab-observability-ux-design.md` | Source of truth for copy/IA |

---

### Task 1: UX checklist artifact (no code UI yet)

**Files:**
- Create: `docs/superpowers/specs/2026-09-03-lab-observability-ux-checklist.md`

- [ ] **Step 1: Write ship checklist** from heuristic §8 + state matrices (feedback + pareto) as markdown checkboxes
- [ ] **Step 2: List exact RU microcopy** strings in that file (single source for engineers)
- [ ] **Step 3: Commit** `docs: UX checklist and microcopy for lab observability`

---

### Task 2: float-dock mutex for three panels

**Files:**
- Modify: `apps/web/src/components/Chat.tsx`
- Test manually / light component test if present

**Interfaces:**
- Produces: `activeFloat: "debug" | "results" | "models" | null`

- [x] **Step 1: Refactor** existing Debug/Results open state into single `activeFloat`
- [x] **Step 2: Opening Models closes others** (and vice versa) — same pattern as current Debug↔Results
- [x] **Step 3: Verify Escape on each panel returns focus to its FAB**
- [x] **Step 4: Commit** `fix(web): unify float-dock mutex for three panels`

---

### Task 3: ModelsFloat shell + tabs

**Files:**
- Create: `apps/web/src/components/ModelsFloat.tsx`
- Modify: `apps/web/src/index.css`
- Modify: `Chat.tsx` to render in `.float-dock`

```tsx
// Shape
type ModelsTab = "ranking" | "feedback";
// Props: open, onOpenChange, hours, onHoursChange
// Tabs: Рейтинг | Оценки
// Header actions: window select 24h|7д, Close
```

- [x] **Step 1: Scaffold** FAB label «Модели», panel with `role="dialog"` `aria-modal="false"` (non-blocking float like Debug)
- [x] **Step 2: CSS** clone dimensions/z-index from `.lab-results-float` / `.debug-float`
- [x] **Step 3: Empty tabs render placeholders** («Скоро» only if API not ready — prefer real empty states)
- [x] **Step 4: Commit** `feat(web): Models float shell with ranking/feedback tabs`

---

### Task 4: ParetoPanel quality states

**Files:**
- Create: `apps/web/src/components/ParetoPanel.tsx`
- Modify: `client.ts` — `getLabPareto(hours)`

- [x] **Step 1: Table** columns per UX spec; format p50 as seconds with 1 decimal
- [x] **Step 2: Skeleton / empty / error+Retry**
- [x] **Step 3: `<details>` formula** using checklist microcopy
- [x] **Step 4: `aria`** on table; sort indicator text «по Score»
- [x] **Step 5: Commit** `feat(web): Pareto ranking panel with full UI states`

---

### Task 5: FeedbackStrip on Turn

**Files:**
- Create: `apps/web/src/components/FeedbackStrip.tsx`
- Modify: `Turn.tsx`, `client.ts` — `postMessageFeedback(messageId, value)`

- [x] **Step 1: Render only when** `role===assistant` && `messageId` && not streaming
- [x] **Step 2: Optimistic `aria-pressed`**; rollback on API error + inline error text
- [x] **Step 3: Hit targets 44px; keyboard activatable**
- [x] **Step 4: Commit** `feat(web): helpful/not-helpful strip on assistant turns`

---

### Task 6: FeedbackStatsPanel

**Files:**
- Create: `apps/web/src/components/FeedbackStatsPanel.tsx`

- [x] **Step 1: Table** ups/downs/down%; show «ниже в очереди» chip if `penalized`
- [x] **Step 2: Empty:** «Оценок пока нет — нажмите 👍/👎 под ответом.»
- [x] **Step 3: Commit** `feat(web): feedback stats tab in Models float`

---

### Task 7: Heuristic review pass (mandatory before calling UX done)

> **Выполнено 2026-09-03 отрядом из пяти ревьюеров по живому стенду** (фаза C.0 мастер-плана,
> правила в [prep D14](./2026-09-03-observability-prep-decisions.md)). Итоги и evidence —
> в разделе «Гейт пройден» файла
> [ux-checklist](../specs/2026-09-03-lab-observability-ux-checklist.md).

**Files:**
- Update checklist boxes in `…-ux-checklist.md`

- [x] **Step 1: Walk Nielsen 1–10** against running UI (local or staging); note severity
- [x] **Step 2: Fix any severity ≥3** (blockers) in the same session
- [x] **Step 3: Mobile width ~390px** screenshot or manual: dock not overlapping composer send; thumbs usable
- [x] **Step 4: Commit** `docs: complete lab observability UX checklist` (+ any fix commits)

---

### Task 8: Cross-link plans

**Files:**
- Modify: `docs/superpowers/plans/2026-09-03-model-pareto-lab.md` Task 7 → «implement via ModelsFloat/ParetoPanel from UX plan»
- Modify: `docs/superpowers/plans/2026-09-03-feedback-router.md` Task 7 → «FeedbackStrip + FeedbackStatsPanel from UX plan»
- Modify: `docs/superpowers/plans/2026-09-03-deferred-features.md` — add this plan as order 0 / parallel UX track

- [x] **Step 1: Edit cross-links**
- [x] **Step 2: Commit** `docs: wire UX plan into deferred feature index`

---

## Execution order vs backend

```
UX Task 1 (checklist)     ─── anytime
UX Task 2–3 (shell)       ─── can ship with mock data
Backend Pareto API        ─── Pareto Lab plan Tasks 1–6
UX Task 4                 ─── needs Pareto API
Backend Feedback API      ─── Feedback plan Tasks 1–4
UX Task 5–6               ─── needs Feedback API
UX Task 7                 ─── final gate
```

Mocks allowed: `ParetoPanel` accepts `data` prop for Story/dev without API.

## Self-review

- Spec IA (FAB Models + tabs) has Tasks 2–6
- Feedback mid-stream blocked in Task 5
- Heuristic gate is Task 7, not optional
- No third unmanaged FAB without mutex
