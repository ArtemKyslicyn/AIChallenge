# Challenge 22 — chunking comparison

## Corpus

Mounted into `rag`:

- `docs/` (design specs, guest MCP, env notes)
- `README.md`, `AGENTS.md`, `CLAUDE.md`

Target: ≥20–30 pages equivalent of product docs/code commentary.

## Strategies

| Strategy | How | Typical use |
|---|---|---|
| `fixed` | window + overlap (800/120) | even sizes, may split mid-section |
| `structural` | `#` / `##` + file boundaries | keeps headings together |

Commands (local rag):

```bash
curl -sS -H "Authorization: Bearer $RAG_SHARED_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"strategy":"fixed"}' http://127.0.0.1:18766/v1/index
curl -sS -H "Authorization: Bearer $RAG_SHARED_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"strategy":"structural"}' http://127.0.0.1:18766/v1/index
curl -sS -H "Authorization: Bearer $RAG_SHARED_TOKEN" http://127.0.0.1:18766/v1/stats
```

## Observed (fill after first index on your machine)

| Metric | fixed | structural |
|---|---|---|
| chunks | _run_ | _run_ |
| avg chars | _run_ | _run_ |
| metadata present | yes | yes |

## Hit@k smoke (same 5 queries)

Queries: Guest MCP, model_id, Reality :443, Profile, FakeLLM.

Structural usually wins section-scoped questions; fixed wins when the answer spans heading boundaries.

## Load

`./scripts/rag-load-smoke.sh` — concurrent `/v1/search`, prints mem if docker rag is up.
With API/fake embeddings, container RAM stays modest vs local sentence-transformers.
