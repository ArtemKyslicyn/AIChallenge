# aichallenge-mcp-kit Hub Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. This repo is **not** the AIChallenge monorepo.

**Goal:** Public `aichallenge-mcp-kit` — one Streamable HTTP hub with hierarchical child MCPs, Python sandbox, and `/artifacts`, connectable to AIChallenge Guest MCP via tunnel.

**Architecture:** FastMCP 1.x HTTP gateway on `127.0.0.1:3100`; `kit.yaml` groups→children (stdio|http|builtin); shared Bearer; artifact store under workspace.

**Tech Stack:** Python 3.12+, `mcp>=1.13,<2` (FastMCP 1.x — same pin family as AIChallenge `apps/mcp`), optional Node child processes via npx.

**Spec:** `docs/superpowers/specs/2026-09-28-mcp-kit-hub-design.md` (in AIChallenge); mirror summary in kit `docs/`.

## Global Constraints

- Never commit real tokens (`KIT_SHARED_TOKEN`, GitHub PATs).
- Default bind `127.0.0.1` — only the tunnel is public.
- Sandbox filesystem to `KIT_WORKSPACE`.
- Do not implement AIChallenge UI in this repo.
- Public repo + strong README/docs are part of the deliverable.

---

### Task 1: Public repo + documentation skeleton

**Files:** new GitHub repo `ArtemKyslicyn/aichallenge-mcp-kit` (public)

- [ ] Create public repo and clone locally
- [ ] Add README (5-step connect), `.env.example`, `kit.example.yaml`, `packs/aichallenge-guest.example.json`
- [ ] Add `docs/architecture.md`, `docs/security.md`, `docs/connect-aichallenge.md`, `docs/python-sandbox.md`, `docs/children.md`
- [ ] Commit `docs: public hub kit skeleton and connect guide`

### Task 2: Hub HTTP + Bearer + hub tools

- [ ] Streamable HTTP `/mcp` with Bearer `KIT_SHARED_TOKEN`
- [ ] Tools: `hub_list_children`, `hub_workspace_*`
- [ ] Smoke: initialize + tools/list; no token → 401
- [ ] Commit `feat: hub Streamable HTTP with workspace tools`

### Task 3: Child proxy (groups)

- [ ] Load `kit.yaml`; spawn/connect children; prefix `{group}__{child}__{tool}`
- [ ] Default profile: fs + git when deps present (or document skip)
- [ ] Commit `feat: hierarchical child MCP proxy`

### Task 4: Artifacts HTTP

- [ ] `POST/PUT/GET /artifacts` with same Bearer
- [ ] Commit `feat: artifact upload download endpoints`

### Task 5: Python sandbox builtin

- [ ] `dev__python__exec|write|read|reset` under workspace sandboxes
- [ ] Network off, timeout, output cap
- [ ] Commit `feat: python sandbox builtin child`

### Task 6: README polish + release tag

- [ ] End-to-end tunnel instructions verified in README
- [ ] Tag `v0.1.0` when smoke passes locally

## Success

Visitor: clone → run → tunnel → AIChallenge Guest MCP → hierarchical tools + python exec + artifact URL without stand `/mcp/*`.
