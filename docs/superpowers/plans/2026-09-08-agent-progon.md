# Agent `/прогон` (Day 6.2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a **Прогон** team mode that fans out one task across a small matrix of models or temperatures via existing `run_agent`, then aggregates answers for the client (Artem-style, no headless split).

**Architecture:** Keep all orchestration on the web client. Parse optional `/прогон` prefix locally; clone the base agent draft into ≤4 variant definitions; `Promise.all` → `runAgentWorkshop`; optional fifth call with a fixed «Склейщик» preset. No new public HTTP route in v1.

**Tech Stack:** Vite React TS (`AgentWorkshop`, `agents/orchestrate.ts`), existing `POST /agent-workshop/run`, FakeLLM only if we add API later

**Spec:** `docs/superpowers/specs/2026-09-08-agent-progon-design.md`

## Global Constraints

- Domain-agnostic RU copy; no medical role names
- Every assistant-facing result shows resolved `model_id`
- Do not call `/llm/complete` from Agents UI — only `runAgentWorkshop`
- No new compose service / headless process
- Cap variants at 4; respect existing visitor hourly agent-run limit
- Do not break solo / parallel / chain / roundtable
- Never commit secrets; no deploy unless user asks

## File map

| Path | Role |
|------|------|
| `docs/superpowers/specs/2026-09-08-agent-progon-design.md` | Locked UX/API decisions |
| `apps/web/src/agents/orchestrate.ts` | `TeamMode` += `progon`; parse trigger; build variants; aggregate prompt |
| `apps/web/src/agents/progon.ts` | (optional extract) matrix presets + `runProgon` helper types |
| `apps/web/src/agents/presets.ts` | Add «Склейщик» preset (system prompt only) |
| `apps/web/src/components/AgentWorkshop.tsx` | Mode UI, matrix toggle, run path, team log labels |
| `apps/web/src/index.css` | Small styles for matrix chips / cost hint |
| `docs/superpowers/specs/2026-09-07-first-agent-design.md` | Cross-link Day 6.2 |
| `challenges/06-first-agent/README.md` | Optional one-liner how to demo Прогон |

---

### Task 1: Pure helpers — parse + matrix + aggregate prompt

**Files:**
- Modify: `apps/web/src/agents/orchestrate.ts` (or create `apps/web/src/agents/progon.ts` if file grows)
- Test: if web has no vitest unit harness for `agents/`, add a tiny node assert script **or** colocate pure functions and cover via `apps/web` existing test runner if present — prefer pure exports tested with `node --test` only if already used; else keep functions pure and verify manually in Task 3. Prefer: check `apps/web/package.json` for `vitest`/`node:test`; if none, skip automated test and use challenge manual steps.

**Steps:**

- [ ] **Step 1:** Add types:

```ts
export type ProgonAxis = "temperature" | "model";

export interface ProgonMatrix {
  axis: ProgonAxis;
  temperatures?: number[]; // default [0.2, 0.7, 1.2]
  modelIds?: string[];     // max 3 from catalog
}

export function stripProgonTrigger(raw: string): { triggered: boolean; task: string } {
  const m = raw.match(/^\s*\/прогон\b[ \t]*/i);
  if (!m) return { triggered: false, task: raw.trim() };
  return { triggered: true, task: raw.slice(m[0].length).trim() };
}

export function buildProgonVariants(
  base: { name: string; system_prompt: string; preferred_model: string; temperature?: number | null; max_tokens?: number | null },
  matrix: ProgonMatrix,
): Array<typeof base & { label: string }> { /* … */ }

export function buildProgonAggregateMessage(opts: {
  task: string;
  parts: { label: string; modelId: string; content: string }[];
}): string { /* numbered blocks + instruction to synthesize briefly */ }
```

- [x] **Step 2:** Extend `TeamMode` with `"progon"`; `TEAM_MODE_LABEL` / `HINT` / `SCHEME` (e.g. scheme `A∥B∥C → Σ`).
- [x] **Step 3:** Commit: `feat(web): add progon parse and variant matrix helpers`

---

### Task 2: «Склейщик» preset + workshop wiring

**Files:**
- Modify: `apps/web/src/agents/presets.ts`
- Modify: `apps/web/src/components/AgentWorkshop.tsx`
- Modify: `apps/web/src/index.css`

**Steps:**

- [ ] **Step 1:** Add preset (not auto-inserted into rail unless user clicks):

```ts
{
  name: "Склейщик",
  system_prompt:
    "Ты склеиваешь ответы нескольких вариантов одного задания. Кратко сравни, выдели согласие и расхождения, дай итоговый ответ пользователю. Упоминай model_id/метки вариантов. Без воды.",
  preferred_model: "auto",
  temperature: 0.3,
  max_tokens: 800,
}
```

- [ ] **Step 2:** In `AgentWorkshop`, when `teamMode === "progon"`:
  - Require **exactly one** base agent in roster (or use `activeId` if roster empty — auto-select active).
  - Show axis toggle: «По temperature» | «По моделям».
  - Temperature: show chips `0.2 / 0.7 / 1.2` (editable later = YAGNI).
  - Models: multi-select up to 3 from `modelOptions` (exclude needing session).
  - Hint: «Запросы: N субагентов + 1 склейка».
- [ ] **Step 3:** On submit / `runTeam`:
  - If mode is progon **or** (`stripProgonTrigger(teamTask).triggered` while in any team mode) → force progon path (if triggered from parallel, still OK to switch behavior for that run).
  - Prefer: only honor `/прогон` prefix when `teamMode === "progon"` **or** always strip and auto-switch to progon for that click — **lock: auto-switch to progon for that run when prefix present**.
  - `buildProgonVariants` → `Promise.all` `runOne(..., { mirror: "brief" })` → `pushTeam` each.
  - Then aggregator: use Склейщик definition (inline from preset, do not require draft in store) → `runOne` on a **ephemeral** path: either temporary draft id `_progon_agg` session or call `runAgentWorkshop` directly and only `pushTeam` (cleaner: direct API + pushTeam, no polluting agent list).
  - On agg failure: markdown fallback join into `pushTeam`.
- [ ] **Step 4:** Disable chain-order UI for progon; hide ↑↓; roster shows single base + «варианты из матрицы».
- [ ] **Step 5:** CSS for axis toggle + request-count hint.
- [ ] **Step 6:** `npx tsc --noEmit` + `npm run build` in `apps/web`.
- [ ] **Step 7:** Commit: `feat(web): agent workshop Прогон fan-out and aggregate`

---

### Task 3: Docs + challenge note

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-first-agent-design.md` — add Day 6.2 blurb + link
- Modify: `challenges/06-first-agent/README.md` — 3 bullet demo for video

**Steps:**

- [ ] **Step 1:** Spec cross-link; challenge README:

```markdown
## Прогон (бонус Day 6.2)
1. Агенты → Команда → режим Прогон
2. Задача: `/прогон объясни temperature простыми словами`
3. В ленте — 3 варианта + склейка с model_id
```

- [ ] **Step 2:** Commit: `docs: Day 6.2 progon design and challenge note`

---

### Task 4: Manual verification (gate before deploy)

**Steps:**

- [ ] **Step 1:** Local or prod: solo still works unchanged.
- [ ] **Step 2:** Team → Прогон → temperature matrix → 3 replies + aggregate; each shows `model_id`.
- [ ] **Step 3:** Prefix `/прогон` strips and runs same path.
- [ ] **Step 4:** Abort mid-progon stops remaining (shared `AbortController`).
- [ ] **Step 5:** Stop if rate-limit error surfaces clearly in team log.
- [ ] **Step 6:** Deploy **only if user asks**.

---

## Out of scope (next tickets)

- Server `POST /agent-workshop/progon` batch endpoint
- Headless process split (full Artem)
- Agent session memory / dual-pane isolation (Vlad track)
- Free-form `/прогон temp=… model=…` DSL
- Wiring Прогон into main Chat composer
