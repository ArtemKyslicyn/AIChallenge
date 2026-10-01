# Challenge 23 — RAG ask results

## Modes

| Mode | How | Result |
|---|---|---|
| Without RAG | checkbox off | general answer, no sources footer |
| With RAG | «Использовать базу» | context injected + `rag_sources` SSE |

## Corpus / index (prod baseline)

- `structural` chunks: **761**, avg ≈ **547.6** chars (matches challenge 22)
- Embed provider: API (`text-embedding-3-small`); heal restores `vector_count` if matrix missing

## Sample pair

**Q:** Куда ходит публичный :443?

- Without RAG: model often invents ports / omits xray→nginx→web chain  
- With RAG: should cite deploy/VLESS docs; sources show `title` / `section` / `source` / `chunk_id`; `model_id` still on the turn

**Q:** Что такое Guest MCP?

- Without: generic MCP blurb  
- With: Streamable HTTP visitor MCP ≠ stand `/mcp/*`; sources from guest-mcp specs

## Load / capacity

API embeddings default — `rag-load-smoke` on VPS. Local embeddings stay admin-off unless explicitly enabled.
Upload path embeds **only new chunks** (append); full rebuild only when matrix missing/mismatched, with hard timeouts + FakeEmbedder fallback.
