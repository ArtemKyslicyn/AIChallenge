"""Streamable HTTP MCP tools for external Guest MCP connect."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("aichallenge-rag", host="0.0.0.0", stateless_http=True)

_pipeline: Any = None
_store: Any = None
_settings: Any = None


def bind_runtime(*, pipeline: Any, store: Any, settings: Any) -> None:
    global _pipeline, _store, _settings
    _pipeline = pipeline
    _store = store
    _settings = settings


@mcp.tool()
async def rag_stats() -> str:
    """Index stats: chunk counts, strategy, embed mode."""
    if _store is None or _settings is None:
        return json.dumps({"error": "rag not ready"})
    payload = {
        **_store.stats(),
        "embedding_provider": _settings.effective_provider(),
        "local_embeddings_enabled": _settings.local_embeddings_enabled,
        "chunk_strategy": _settings.rag_chunk_strategy,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp.tool()
async def rag_search(query: str, top_k: int = 6, mode: str = "full") -> str:
    """Search the document index; returns chunks with metadata and scores.

    mode: raw | filtered | full (rewrite + threshold + heuristic rerank).
    """
    if _pipeline is None:
        return json.dumps({"error": "rag not ready"})
    result = await _pipeline.search_payload(query, top_k=top_k, mode=mode)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def rag_index(strategy: str = "structural") -> str:
    """Re-index the stand corpus with fixed or structural chunking."""
    if _pipeline is None:
        return json.dumps({"error": "rag not ready"})
    if strategy not in {"fixed", "structural"}:
        return json.dumps({"error": "strategy must be fixed|structural"})
    result = await _pipeline.reindex(strategy=strategy)
    return json.dumps(result, ensure_ascii=False, indent=2)
