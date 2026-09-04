# Comic Generator Implementation Plan

> **For agentic workers:** Implement task-by-task. Steps use checkbox syntax.

**Goal:** Chat tool `generate_comic` that plans 3–6 panels, draws text-free art via Pollinations, and streams HTML dialogue overlays over SSE.

**Architecture:** Extend media tool loop in `chat.py`. Server builds/validates storyboard JSON, streams storyboard text, then sequential image gens with `comic_*` SSE events. Persist comic JSON in assistant message content for history rehydrate.

**Tech Stack:** FastAPI, existing Pollinations/`MediaGenerator`, Vite React SSE client

**Spec:** `docs/superpowers/specs/2026-09-04-comic-generator-design.md`

## Global Constraints

- Domain-agnostic naming; expose `model_id` on every assistant turn
- No real LLM/Pollinations keys in CI — FakeLLM + FakeMedia
- Gated by `MEDIA_TOOLS_ENABLED`; panel = 1 image rate-limit unit
- Text never baked into images

## Files

| File | Role |
|------|------|
| `domain/media.py` | `COMIC_TOOL_NAME` + schema; parse tool calls |
| `application/comic.py` | Storyboard parse/clamp, prompts, persist fence, text_mode |
| `application/media_tools.py` | Comic intent (before image), soft gate, remaining budget |
| `application/chat.py` | Comic events + execute path |
| `adapters/api/sse.py` | Wire `comic_*` frames |
| `adapters/api/sessions.py` | Analytics `comic_generated` |
| `apps/web` | SSE types, `ComicStrip`, Chat/Turn wiring, empty chip |

## Tasks

### Task 1: Domain + comic helpers (TDD)
- [x] Intent / clamp / prompt builder / fence serialize-parse tests
- [x] Implement `application/comic.py` + media schema/intent updates

### Task 2: Chat pipeline + SSE
- [x] Events + comic branch in media loop; skip follow-up stream on success
- [x] SSE mapping + unit tests; analytics emit

### Task 3: Web UI
- [x] Parse SSE + history fence; `ComicStrip` overlays; empty-state chip

### Task 4: Verify
- [x] `pytest` media/comic/sse units; web `tsc` if available
- [x] Update spec status to Implemented (v1)
