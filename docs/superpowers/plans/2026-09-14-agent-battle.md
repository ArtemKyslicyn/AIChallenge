# Agent Battle — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Новая вкладка **«Битва»** — песочница конкурирующих агентов с редактируемым миром/фактами, дефолтным странным кастом и запуском раундов по SSE.

**Architecture:** Shell mode `battle` + localStorage `ArenaDoc`; API `POST /api/v1/agent-battle/run` гоняет фазы (brief → propose ∥ → rebut → verdict) через существующий `ModelRouter.complete_chat`; UI лента + скорборд. Без Postgres в v1.

**Tech Stack:** FastAPI + SSE, Vite/React/TS, FakeLLM в тестах, те же visitor/rate-limit паттерны что у `agent-studio`.

**Spec:** `docs/superpowers/specs/2026-09-14-agent-battle-design.md`

## Global Constraints

- Domain-agnostic code/API names (no medical roles)
- Every agent/arbiter output exposes `model_id`
- Secrets never in repo; FakeLLM in CI
- No actionable WMD content in default prompts (safety rails in spec §3)
- Do not remove Chat / Agents / Graph / Benchmarks
- VLESS/deploy rules unchanged; no Reality edits
- Prefer ports + FakeLLM; no real LLM keys in CI

## File map

| Path | Responsibility |
|------|----------------|
| `docs/superpowers/specs/2026-09-14-agent-battle-design.md` | Locked product decisions |
| `apps/api/src/app/domain/agent_battle.py` | Arena types, scoring helpers, red-line check |
| `apps/api/src/app/application/battle_run.py` | Round loop + SSE event dicts |
| `apps/api/src/app/adapters/api/agent_battle.py` | HTTP route |
| `apps/api/src/app/core/settings.py` | `battle_max_rounds`, enable flag |
| `apps/api/tests/unit/test_agent_battle.py` | FakeLLM loop + safety marker |
| `apps/web/src/shellMode.ts` | `battle` mode + `#battle` hash |
| `apps/web/src/App.tsx` | Tab **Битва** |
| `apps/web/src/battle/types.ts` | ArenaDoc TS types |
| `apps/web/src/battle/defaultArena.ts` | Default world / facts / cast |
| `apps/web/src/battle/persist.ts` | localStorage load/save/reset |
| `apps/web/src/battle/runBattle.ts` | SSE client |
| `apps/web/src/components/AgentBattle.tsx` | Main UI |
| `apps/web/src/api/client.ts` | `runAgentBattle` helper |
| `apps/web/src/index.css` | Layout tokens (match existing lab chrome) |

---

### Task 1: Domain scoring + red lines

**Files:** `domain/agent_battle.py`, `tests/unit/test_agent_battle.py`

- [ ] **Step 1:** Write failing tests: `score_pct`-like helper for battle scores; `apply_world_delta`; `red_line_triggered(text, red_lines)`.
- [ ] **Step 2:** Run pytest — expect fail.
- [ ] **Step 3:** Implement pure functions (no I/O).
- [ ] **Step 4:** Pytest pass.
- [ ] **Step 5:** Commit: `feat(api): agent battle domain scoring and red lines`

---

### Task 2: Application run loop (FakeLLM)

**Files:** `application/battle_run.py`, tests

- [ ] **Step 1:** Test: 2 personas + arbiter, `max_rounds=1`, FakeLLM → sequence includes `battle_start`, `agent_done`×2 with `model_id`, `verdict`, `battle_done`.
- [ ] **Step 2:** Implement `async def iter_battle_run(arena, router, *, max_rounds, enabled)` yielding `{event, data}`.
- [ ] **Step 3:** Inject SAFETY_PREFIX into every system prompt.
- [ ] **Step 4:** Pytest pass; commit: `feat(api): agent battle run loop over ModelRouter`

---

### Task 3: HTTP SSE adapter + settings

**Files:** `adapters/api/agent_battle.py`, `main`/router include, `settings.py`, deps rate limit

- [ ] **Step 1:** Settings: `agents_battle_enabled: bool = True`, `battle_max_rounds: int = 5` (cap 8 in use-case).
- [ ] **Step 2:** Route `POST /api/v1/agent-battle/run` → StreamingResponse like studio.
- [ ] **Step 3:** API test with TestClient + FakeLLM (or unit on formatter).
- [ ] **Step 4:** Commit: `feat(api): agent-battle SSE endpoint`

---

### Task 4: Web types + default arena + persist

**Files:** `battle/types.ts`, `defaultArena.ts`, `persist.ts`

- [ ] **Step 1:** Port ArenaDoc types from spec.
- [ ] **Step 2:** Author full default scenario text (fictional blocs, tech race, deterrence posture) + 7 personas + arbiter prompts with safety lines.
- [ ] **Step 3:** `loadArena` / `saveArena` / `resetDefaultArena` under key `aichallenge.battle_arena.v1`.
- [ ] **Step 4:** Commit: `feat(web): default agent-battle arena and persist`

---

### Task 5: Shell tab + AgentBattle shell UI (no run yet)

**Files:** `shellMode.ts`, `App.tsx`, `AgentBattle.tsx`, CSS

- [ ] **Step 1:** Add `battle` to `ShellMode` + hash `#battle` / `?shell=battle`.
- [ ] **Step 2:** Topbar button **Битва** + `title` tooltip; mount `<AgentBattle />`.
- [ ] **Step 3:** UI: editor tabs Мир/Факты/Каст/Правила; empty lead; Reset; disabled Run until Task 6.
- [ ] **Step 4:** Build + visual smoke; commit: `feat(web): Битва tab shell and arena editors`

---

### Task 6: SSE client + live run UX

**Files:** `api/client.ts`, `battle/runBattle.ts`, `AgentBattle.tsx`

- [ ] **Step 1:** `runAgentBattle(arena, { signal, onEvent })` parse SSE.
- [ ] **Step 2:** Wire Запуск/Стоп; render round log cards with `model_id`; scoreboard; world meters.
- [ ] **Step 3:** On `battle_done` optionally reveal hidden goals if rules say so.
- [ ] **Step 4:** Commit: `feat(web): run agent-battle sandbox over SSE`

---

### Task 7: Safety + polish polish

**Files:** tests, default prompts, README one-liner, `.env.example` names only

- [ ] **Step 1:** Unit: prompt containing banned pattern → arbiter/agent response includes refusal marker (FakeLLM scripted).
- [ ] **Step 2:** Cap rounds from settings; show in Rules UI.
- [ ] **Step 3:** README: mention вкладка Битва as lab sandbox.
- [ ] **Step 4:** Commit: `test(api): agent-battle safety rails; docs: battle tab`

---

### Task 8: Manual DoD

- [ ] Local: FakeLLM — full 1-round battle.
- [ ] Local: real key optional — 1 round, 2 agents.
- [ ] Abort mid-run leaves partial log.
- [ ] Other tabs untouched.
- [ ] No secrets in diff.

---

## Out of scope (follow-ups)

- Token streaming per agent  
- Postgres arena CRUD  
- Shared multiplayer rooms  
- Auto-ingest battle outcomes into Benchmarks  

## Approval gate

Перед Task 1 подтвердить spec §12 (A–D). Рекомендации уже вписаны в план как defaults.
