# Agent `/прогон` (Day 6.2) — Design Spec

**Date:** 2026-09-08  
**Status:** Implemented  
**Depends on:** `run_agent` / `POST /agent-workshop/run`, AgentWorkshop (solo|team)  
**Parent:** `docs/superpowers/specs/2026-09-07-first-agent-design.md`  
**Plan:** `docs/superpowers/plans/2026-09-08-agent-progon.md`

## Goal

**Прогон** = production-style **fan-out / fan-in**: одна задача → независимые субагенты (матрица temperature или models) → dedicated **Склейщик** (reducer). Плюс улучшение команды: optional fan-in после parallel/roundtable; явные фазы в ленте.

Aligned with common 2025–26 guidance (supervisor + parallel workers + merge step; distinct worker missions so variants do not duplicate).

## Patterns in UI

| Mode | Pattern |
|------|---------|
| Параллельно | Fan-out + optional Σ |
| Цепочка | Sequential handoff |
| Обсуждение | Parallel R1 → peer R2 → optional Σ |
| Прогон | Matrix fan-out → Σ; `/прогон` prefix |

## Locked decisions

| Topic | Choice |
|-------|--------|
| Surface | Агенты → Команда |
| Trigger | Mode **Прогон** or leading `/прогон` |
| Parse | Client regex; not LLM intent |
| Worker briefs | Distinct `[Миссия прогона]` per temp/model |
| Aggregate | `AGGREGATOR_DEFINITION` via `runAgentWorkshop`; markdown fallback |
| Cap | ≤4 variants; request budget shown in UI |
| HTTP | No new route |

## Files

- `apps/web/src/agents/progon.ts`
- `apps/web/src/agents/orchestrate.ts`
- `apps/web/src/components/AgentWorkshop.tsx`
- `apps/web/src/agents/presets.ts` (Склейщик)
