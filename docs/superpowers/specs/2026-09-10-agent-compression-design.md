# Agent Context Compression (Day 9) — Design Spec

**Date:** 2026-09-10  
**Status:** Approved (LLM summary)  
**Depends on:** Day 7 dialogs, Day 8 token meter  
**Challenge:** `challenges/09-compression/` (Video + Code)

## Goal

Компрессия истории solo-агента: последние **N** сообщений «как есть», всё старше — в **summary** (LLM), summary подставляется в запрос вместо полной ранней истории. Сравнение качества и токенов с/без сжатия.

## Policy

Defaults: `recent_keep=6`, `summarize_every=10` (when uncovered older messages ≥ threshold, refresh summary).

LLM request assembly (after compression, before Day-8 fit):

```text
system(definition)
[+ system("Сводка более раннего диалога:\n" + summary)]  # if summary non-empty
… last N user/assistant turns …
user(current)
```

Full message list remains in Postgres for UI. New columns on `agent_dialogs`:

| Column | Role |
|--------|------|
| `summary_text` | Latest rolling summary |
| `summary_until_count` | How many prefix messages the summary covers |

When `len(messages) - summary_until_count - recent_keep >= summarize_every` (or always when enabling and backlog large): call summarizer LLM once, update summary fields, then run main agent.

## API

Request extras: `compress: bool`, optional `recent_keep`, `summarize_every`.

Response extras under `compression`:

```json
{
  "enabled": true,
  "summary_used": true,
  "summary_refreshed": false,
  "recent_kept": 6,
  "covered_by_summary": 20,
  "tokens_raw_est": 1200,
  "tokens_compressed_est": 400
}
```

Token meter (Day 8) still reports actual request tokens after compression (+ fit).

## UI

Solo workshop: toggle «Сжимать историю», optional N/threshold, expandable «Сводка» when present; meter line `сырой → сжатый` when compression enabled.

## Challenge / video

Same long dialog twice (off vs on): answer quality + token delta; Playwright recording.

## Non-goals

Team/progon compression v1; tiktoken; deleting old messages from DB.
