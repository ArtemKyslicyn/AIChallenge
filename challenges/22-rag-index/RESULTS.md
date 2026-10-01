# Challenge 22 — chunking comparison

## Corpus

Mounted into `rag` (compose):

- `docs/` (design specs, guest MCP, env notes)
- `README.md`, `AGENTS.md`, `CLAUDE.md`

Indexed files: **58** (text/md under those mounts, ≤2 MB each).

## Strategies

| Strategy | How | Typical use |
|---|---|---|
| `fixed` | window + overlap (800/120) | even sizes, may split mid-section |
| `structural` | `#` / `##` + file boundaries | keeps headings together |

## Observed (compose-equivalent corpus, FakeEmbedder local + prod structural)

| Metric | fixed | structural |
|---|---|---|
| chunks | **620** | **761** |
| avg chars | **770.5** | **547.6** |
| indexed_files | 58 | 58 |
| metadata (`source`, `title`, `section`, `chunk_id`, `strategy`) | yes | yes |

Prod after Day-22 deploy had `structural` only: `total_chunks=761`, `avg_chars≈547.6` (matches table).
After heal (`vector_count=761`, embed runtime may be `fake-hash` if API embed budget trips — search still works).

## Hit@k smoke (top-3, mode=raw, FakeEmbedder)

| Query | Top sources (score) |
|---|---|
| Guest MCP | guest-mcp / agent specs (~0.49–0.54) |
| model_id | `docs/env-local.md`, profile spec (~0.52–0.62) |
| Reality :443 | deploy / agent specs (weaker on fake hash — API embeds improve) |
| Profile | profile / AGENTS (~0.50–0.55) |
| FakeLLM | plans / AGENTS (~0.51–0.54) |

Structural keeps heading sections intact → better for section-scoped questions; fixed is more uniform for answers that span headings.

## Load

`./scripts/rag-load-smoke.sh` — concurrent `/v1/search`.
API embeddings default; local sentence-transformers stay admin-off on prod.
