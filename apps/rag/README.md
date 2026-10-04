# AIChallenge RAG

Public standalone repo (docs + releases):
**[ArtemKyslicyn/aichallenge-rag](https://github.com/ArtemKyslicyn/aichallenge-rag)**

This folder is the in-monorepo copy used by Compose (`127.0.0.1:18766`). Connect from AIChallenge chat (`use_rag`) or from outside via Guest MCP (`/mcp` Streamable HTTP).

## Run locally

```bash
cd apps/rag
uv sync
export EMBEDDING_PROVIDER=fake   # or api + LLM_API_KEY / ROUTERAI_KEY
export RAG_CORPUS_DIR=../../docs
export RAG_DATA_DIR=./data
uv run python -m aichallenge_rag
```

- Health: `GET /health`
- Index: `POST /v1/index` `{"strategy":"structural"}`
- Search: `POST /v1/search` `{"query":"..."}`
- Upload: `POST /v1/documents/upload`
- MCP: `/mcp` with `Authorization: Bearer $RAG_SHARED_TOKEN`

## Docker

Published on loopback only in compose: `127.0.0.1:18766`. Never bind `:443`/`:8443`.

Optional local embeddings (admin): `PATCH /v1/settings` `{"local_embeddings":true}` —
requires image built with `sentence-transformers` extras; default is API/fake.

## External connect

Tunnel `http://127.0.0.1:18766/mcp` and paste the HTTPS URL into AIChallenge
Profile → Подключения (Guest MCP). Tools: `rag_stats`, `rag_search`, `rag_index`.

Full public docs: https://github.com/ArtemKyslicyn/aichallenge-rag
