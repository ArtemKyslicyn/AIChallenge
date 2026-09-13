# Agent Canvas Studio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `subagent-driven-development` after design approval. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Отдельный раздел **«Схема Агентов»** — визуальный конструктор агентов и связей (n8n / Langflow–like canvas).

**Architecture:** Третий shell-mode `studio` с infinite canvas (`@xyflow/react`), граф как JSON-артефакт (source of truth), runtime на API поверх существующих `run_agent` / drafts. Workshop (solo/team) остаётся для линейных сценариев Day 6–10.

**Tech Stack:** Vite + React + TS, `@xyflow/react` (+ optional dagre/elk layout), Zustand для графа, FastAPI Postgres JSONB для persistence, SSE для live run highlight.

**Spec (to approve):** этот план + UX-секция ниже; отдельный design doc после ответа на вопрос IA.

**References (GitHub / industry):**
- [n8n AI Workflow Builder](https://github.com/n8n-io/n8n/pull/14820) — canvas + chat assistant, auto-layout, sticky docs
- [Langflow DESIGN.md](https://github.com/langflow-ai/langflow/blob/main/DESIGN.md) — sidebar + infinite canvas, typed ports, restrained monochrome + semantic color
- [Agent Patterns: Visual Workflow Graph](https://www.agentpatternscatalog.org/patterns/visual-workflow-graph/) — Start/End + typed nodes as serialisable artefact
- Canvas UX trends 2025–26: spatial workspace, run path highlight, inspector drawer, prompt→graph (assistant later)

## Global Constraints

- Domain-agnostic naming (no medical/product role names)
- Every assistant reply exposes `model_id`
- Secrets never in repo; FakeLLM in CI
- VLESS/deploy rules unchanged
- Preserve shell tabs **Чат** / **Агенты**; Studio — additive
- Avoid purple-glow / generic AI chrome; follow existing AIChallenge visual language + Langflow-like restraint

---

## Product decision (lock before Task 1)

### IA

| Option | Meaning |
|--------|---------|
| **A (рекомендуем)** | Topbar: `Чат` \| `Агенты` \| `<CanvasTab>` — canvas отдельно; Agents = текущий workshop |
| B | Canvas внутри Агентов (подрежим) |
| C | Заменить Agents целиком на canvas |

### Имя вкладки (не «Студия» — слишком размыто)

| Label | Почему |
|-------|--------|
| **Схема** | Коротко: граф связей; понятно в RU |
| **Поток** | Как flow / pipeline; близко к n8n |
| **Конструктор** | Явно «собираем», чуть длиннее |
| **Связи** | Акцент на edges между агентами |
| **Граф** | Точно технически; суховато для UI |
| **Orchestrator / Оркестр** | Жаргон; хуже для новичков |

**Рекомендуем вкладку: `Схема`.**  
Подзаголовок внутри: «Схема агентов» / «Собери цепочку и связи».  
В коде/API: `shellMode: "graph"` или `"flow"` (не `studio`).

План ниже пишет **A + label «Схема»** (можно сменить одной правкой).

---

## UX principles (modern, convenient)

1. **Canvas first** — 70%+ viewport = graph; inspector справа; palette слева (как Langflow/n8n).
2. **One job per surface** — palette / canvas / inspector / run dock; no dashboard clutter in hero.
3. **Typed handles** — нельзя соединить несовместимые порты (message → message, control → control).
4. **Live run** — подсветка активного узла + edge pulse; лог в нижнем dock (как n8n execution).
5. **Empty state** — одна CTA «Добавить Start» или «Собрать из шаблона» (chain / parallel / fan-in), не стена настроек.
6. **Keyboard** — Space pan, ⌘/Ctrl+scroll zoom, Del delete, ⌘S save, ⌘Enter run.
7. **Density** — compact node cards: имя, model badge, 1–2 status dots; детали только в inspector.
8. **Motion** — 2–3: edge draw, node appear, run highlight — без glow-noise.
9. **Assistant (phase 2)** — chat dock «опиши команду» → patch графа (n8n Assistant pattern); v1 без обязательного LLM-builder.

### Node vocabulary (v1)

| Type | Role |
|------|------|
| `start` | Вход пользователя / trigger |
| `agent` | Существующий draft / inline definition |
| `router` | Условное ветвление (простые правила / LLM classify — phase 1.5) |
| `merge` | Fan-in / aggregator |
| `end` | Выход результата |

Edges: `default` (message handoff), later `on_error`.

### Layout sketch

```text
┌ Topbar: Чат | Агенты | Схема ────────────────────┐
├ Palette ┬──────── Canvas (xyflow) ────┬ Inspector ┤
│ Start   │  ○Start → □AgentA → □AgentB │ Name      │
│ Agent   │         ↘ □Merge → ●End     │ System    │
│ Merge   │                             │ Model     │
│ …       │                             │ Mode…     │
├─────────┴── Run dock (log / tokens) ──┴───────────┤
└───────────────────────────────────────────────────┘
```

---

## File map

| Path | Responsibility |
|------|----------------|
| `apps/web/src/shellMode.ts` | Add `studio` |
| `apps/web/src/App.tsx` | Third tab + mount `AgentStudio` |
| `apps/web/src/studio/` | Graph store, types, templates |
| `apps/web/src/components/AgentStudio.tsx` | Shell of studio |
| `apps/web/src/components/studio/*` | Canvas, nodes, palette, inspector, run dock |
| `apps/api/.../domain/agent_graph.py` | Graph schema validation |
| `apps/api/.../application/graph_run.py` | Execute DAG / linear paths |
| `apps/api/.../adapters/api/agent_studio.py` | CRUD + run SSE |
| Alembic `010_agent_graphs.py` | Persist graphs |
| `challenges/11-agent-studio/` | Demo video (optional follow Day 10) |

---

## Phases

### Phase 0 — Spec lock (½ day)
- [ ] Confirm IA option A/B/C
- [ ] Write `docs/superpowers/specs/2026-09-13-agent-studio-design.md`
- [ ] User approves spec

### Phase 1 — Canvas shell (UI only, local graph)
**Files:** `shellMode`, `App`, `AgentStudio`, xyflow dependency, CSS tokens

- [ ] Add npm `@xyflow/react`
- [ ] Shell tab **Схема** (не «Студия»)
- [ ] Empty canvas + palette drag of Start/Agent/Merge/End
- [ ] Connect handles; delete; pan/zoom
- [ ] LocalStorage save graph JSON
- [ ] Manual test: create chain Start→A→B→End

**Done when:** usable graph editor without backend.

### Phase 2 — Graph model + Postgres
**Files:** domain schema, migration, API CRUD

```json
{
  "id": "uuid",
  "name": "TZ pipeline",
  "nodes": [{ "id": "n1", "type": "agent", "position": {"x":0,"y":0}, "data": { "draft_id": "..." } }],
  "edges": [{ "id": "e1", "source": "n1", "target": "n2", "sourceHandle": "out", "targetHandle": "in" }]
}
```

- [ ] Validate acyclic (or allow cycles with max steps — v1: DAG only)
- [ ] `GET/POST/PATCH/DELETE /api/v1/agent-studio/graphs`
- [ ] Ownership via `X-Visitor-Id`
- [ ] Unit tests for validation

**Done when:** graph round-trips API.

### Phase 3 — Runtime execute
**Files:** `graph_run.py`, SSE events

- [ ] Topological run of agent nodes via existing `run_agent` / workshop
- [ ] Handoff: previous output → next user message (reuse chain semantics from `orchestrate.ts`)
- [ ] Merge node: concatenate / optional aggregator agent
- [ ] SSE: `node_start` / `node_end` / `edge` / `done` + `model_id` per agent
- [ ] UI: highlight node + stream log in dock
- [ ] FakeLLM unit tests for linear + fan-in

**Done when:** Run button executes graph on prod-like path.

### Phase 4 — Inspector + agent library
- [ ] Bind `agent` nodes to drafts (reuse `drafts.ts`) or inline definition
- [ ] Inspector: system, model, temp, context_mode (Day 10)
- [ ] Import workshop presets onto canvas
- [ ] Templates: Chain, Parallel→Merge, Roundtable (2 hops)

**Done when:** editing node config feels as good as workshop builder.

### Phase 5 — Polish UX + challenge
- [ ] Mini-map, auto-layout (elk/dagre), snap-to-grid
- [ ] Keyboard shortcuts, undo (command stack)
- [ ] Empty-state templates
- [ ] Challenge 11 video: build chain visually + run
- [ ] Deploy

### Phase 6 (optional later)
- Router/LLM branch nodes
- n8n-style assistant chat → graph patches
- Share/export JSON
- Wire Day-10 strategies per-node

---

## Task 1: Shell + empty Studio

**Files:**
- Modify: `apps/web/src/shellMode.ts`, `App.tsx`, `index.css`
- Create: `apps/web/src/components/AgentStudio.tsx`

- [ ] Extend `ShellMode = "chat" | "agents" | "graph"`
- [ ] Topbar third button **Схема**
- [ ] Mount placeholder with headline + «Canvas скоро» only if Phase 1 not ready — prefer real empty xyflow in same PR as Task 2

### Task 2: xyflow canvas MVP

**Files:**
- Create: `apps/web/src/studio/types.ts`, `graphStore.ts`, `nodes/*.tsx`, `AgentCanvas.tsx`
- Modify: `package.json` (dependency)

- [ ] Install `@xyflow/react`
- [ ] Zustand store: nodes, edges, onNodesChange, onEdgesChange
- [ ] Custom node components (restrained cards)
- [ ] Palette → `onDrop` add node
- [ ] Persist `localStorage` key `aichallenge.studio.graph.v1`

### Task 3: Backend graph CRUD

**Files:**
- Create: domain + alembic `010` + API router
- Test: `tests/unit/test_agent_graph.py`

- [ ] Schema validate DAG + required Start/End
- [ ] CRUD endpoints
- [ ] Visitor ownership

### Task 4: Execute + SSE

**Files:**
- Create: `application/graph_run.py`
- Modify: studio API + web run dock

- [ ] Execute linear path
- [ ] Fan-out/fan-in merge
- [ ] SSE highlight contract
- [ ] Unit tests with FakeLLM

### Task 5: Templates + challenge

- [ ] Three templates
- [ ] `challenges/11-agent-studio/`
- [ ] `RECORD_ONLY=11`

---

## Non-goals (v1)

- Full n8n integrations (HTTP, Gmail, …)
- Visual programming of arbitrary code
- Replacing Chat or Day 6–10 workshop
- Multiplayer CRDT canvas

---

## Success criteria

1. User opens **Студия**, собирает цепочку из 2–3 агентов мышкой за <2 минуты.
2. Run показывает путь на canvas + ответы с `model_id`.
3. Workshop и Chat не регрессируют.
4. UI ощущается как современный builder (Langflow/n8n class), не «форма с кнопками».

---

## Open question for you

1. IA: **A** / **B** / **C**  
2. Имя вкладки: **Схема** (рек.) / Поток / Конструктор / Связи / своё  

После ответа фиксируем spec и можно начинать Phase 1.
