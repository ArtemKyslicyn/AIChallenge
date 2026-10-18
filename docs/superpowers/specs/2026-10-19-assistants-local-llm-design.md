# Assistants + Local LLM (Stand Copilot)

**Date:** 2026-10-19  
**Status:** Implementing

## Goal

LLM skills in topbar **Ассистент** (days 31 / 34 / 35) default to the user’s connected Ollama (`ollama/…`), while still allowing an explicit cloud / `auto` choice.

## Rules

1. **Default:** if a Local LLM source is connected and has tags, assistants UI and `POST /assistants/real-task` prefer the first `ollama/<tag>` when the client sends `auto` / empty.
2. **Choice:** user may pick any catalog model (cloud chain or local). No hard reject of cloud.
3. **Scope:** whenever the effective pin starts with `ollama/`, the request runs under `local_llm_scope(source)` + `charge_local_pin` (same as chat / probe).
4. **Exceptions (no LLM generation):** day 32 invariant review; day 33 FAQ (`model_id=support-faq`, not an LLM id).
5. **Homework:** README for 31/35 recommends showing `ollama/…` badge; cloud is allowed for demo but not the default shoot path.

## Surfaces

| Skill | Path | Model |
|-------|------|--------|
| По docs (31) | Chat `/help` | Composer pin (default local) |
| Diff (32) | CLI/CI | N/A |
| Разблок (33) | `POST /support/ask` | FAQ only |
| Файлы (34) | Chat + Guest MCP | Composer pin (default local) |
| Changelog (35) | `POST /assistants/real-task` | Body `model`; default local |

## Out of scope

Agent07, Reality/VLESS edits, rewriting support as LLM, full reshoot of days 26–30.
