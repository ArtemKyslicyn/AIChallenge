# Agent Graph — «Схема Агентов» Design Spec

**Date:** 2026-09-13  
**Status:** Approved  
**Label (UI):** Схема Агентов  
**Shell mode:** `graph`  
**IA:** Third topbar tab — `Чат` | `Агенты` | `Схема Агентов`  
**Plan:** `docs/superpowers/plans/2026-09-13-agent-studio.md`

## Goal

Visual constructor of agent nodes and edges (n8n/Langflow-like canvas). Workshop under **Агенты** unchanged.

## v1 scope (this iteration)

- Shell tab + infinite canvas (`@xyflow/react`)
- Nodes: Start, Agent, Merge, End
- Drag from palette, connect, delete, pan/zoom
- LocalStorage persist
- Templates stub (chain / parallel→merge)
- No backend execute yet (Phase 3)

## Non-goals (v1)

- Graph run API / SSE
- LLM assistant builder
- Replacing Agents workshop
