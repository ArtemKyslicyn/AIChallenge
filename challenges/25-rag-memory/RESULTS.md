# Challenge 25 — results

## Surface

- Shell: `?shell=rag` / nav **База**
- API: `POST /api/v1/agent-workshop/run` with `persist`, `context_mode=facts`, `use_rag=true`, `rag_mode=full`
- Response includes `rag_sources`, `rag_query_rewritten`, `rag_retrieval` + dialog messages

## Scenario A (edge / model_id)

| Check | Result |
|---|---|
| 12 user turns persisted | yes (dialog draft `rag-memory-day25`) |
| Sources on assistant turns | yes (`rag_sources` nonempty when index healthy) |
| Goal retained mid-dialog | yes (working memory / task strip) |
| Port inventing blocked | invariants trigger on :443 / xray |

## Scenario B (Guest MCP)

| Check | Result |
|---|---|
| Guest MCP ≠ `/mcp/*` held | invariant + facts |
| Sources cite guest-mcp / profile docs | yes when vectors present |
| Reset → new scenario keeps always-on RAG | yes |

## Prod smoke

`vector_count` > 0 on `/api/v1/rag/stats`; open База; ask «Куда ходит :443?» → sources footer open.
