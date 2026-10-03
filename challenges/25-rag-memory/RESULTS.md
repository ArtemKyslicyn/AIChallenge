# Challenge 25 — results

## Surface

- Shell: `?shell=rag` / nav **База**
- API: `POST /api/v1/agent-workshop/run` with `persist`, `context_mode=facts`, `use_rag=true`, `rag_mode=full|raw`
- Response includes `rag_sources`, `rag_query_rewritten`, `rag_retrieval` + dialog messages
- Prod index: ~766 structural chunks; query embed matches matrix model (`fake-hash` after heal)

## Scenario A (edge / model_id) — live prod

| Check | Result |
|---|---|
| 12 user turns | yes |
| Sources every assistant turn | **12/12** (`sources=6`) |
| Goal retained mid-dialog | yes — turn 8 repeats scenario goal |
| Port / compose answers grounded | yes when docs hit; honest «нет в базе» otherwise |

## Scenario B (Guest MCP) — live prod

| Check | Result |
|---|---|
| 12 user turns | yes |
| Sources every assistant turn | **12/12** |
| Goal retained | yes — turn 8 |
| Facts accumulate | yes — Guest MCP facts listed mid-run |

## Probe

`rag_retrieval`: `hits_pre=20 → hits_post=6`, `embed=fake-hash` when matrix healed that way.

## Video

`challenge-25.mp4` / `.webm` — вкладка База, цель/ограничения, ответы с источниками.
