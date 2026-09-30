# RAG service — design

**Date:** 2026-09-30  
**Status:** approved  
**Related:** platform design, Guest MCP, challenge days 21–22 (folders `22-rag-index` / `23-rag-query`)

## 1. Problem

Need a document index (chunk → embed → store) and a first RAG ask path, demoable in product chat, runnable as its own Docker service, and connectable from outside (tunnel / Guest MCP) without binding public `:443`/`:8443`.

## 2. Decision

| Concern | Where |
|---|---|
| Chat toggle, upload, sources UI | AIChallenge `apps/web` + `apps/api` |
| Index, chunking, embeddings, search, MCP | `apps/rag` (compose service `rag`) |
| External RAG | Guest MCP URL pointing at any Streamable HTTP RAG MCP |

Embeddings: OpenAI-compatible API by default. Local model is admin-only (email allowlist), default off, lazy-loaded.

## 3. Architecture

```text
Composer (use_rag + file) → api → rag:18766 (/v1/* + /mcp)
                                     ↑
                         Guest MCP tunnel (external)
```

- Loopback publish: `127.0.0.1:18766`
- Shared Bearer: `RAG_SHARED_TOKEN` (api ↔ rag; MCP same token)
- LLM stays in api; rag returns chunks; api injects context and streams `rag_sources`

## 4. Chunking

- `fixed` — character window + overlap  
- `structural` — markdown headings / file boundaries  

Every chunk: `source`, `title`, `section`, `chunk_id`, `strategy`.

## 5. Product UX

- Composer «Ещё»: checkbox «Использовать базу» (`useRag`)
- Media row: «Файл» → md/txt/pdf → index
- Answer footer: sources when RAG used
- Profile → Подключения: stand RAG stats; external = Guest MCP
- Profile → admin allowlist: «Локальные эмбеддинги на сервере»

## 6. Non-goals (v1)

Separate public git repo, OCR, side-by-side single-turn RAG compare, multi-tenant billing.
