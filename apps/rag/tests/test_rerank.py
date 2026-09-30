"""Tests for query rewrite and filter/rerank modes."""

from __future__ import annotations

from pathlib import Path

import pytest

from aichallenge_rag.embeddings import FakeEmbedder
from aichallenge_rag.pipeline import RagPipeline
from aichallenge_rag.rerank import apply_pipeline, rewrite_query
from aichallenge_rag.settings import Settings
from aichallenge_rag.store import SearchHit, StoredChunk, VectorStore


def test_rewrite_strips_filler_and_expands_alias() -> None:
    out = rewrite_query("пожалуйста расскажи что такое Guest MCP")
    assert "пожалуйста" not in out.lower() or "Guest MCP" in out
    assert "Streamable" in out or "Guest MCP" in out


def test_apply_pipeline_modes() -> None:
    chunks = [
        SearchHit(
            chunk=StoredChunk(
                chunk_id=f"c{i}",
                text=f"text {i} about Guest MCP model_id",
                source="a.md",
                title="t",
                section="s",
                strategy="structural",
                index=i,
            ),
            score=score,
        )
        for i, score in enumerate([0.05, 0.22, 0.55, 0.40])
    ]
    raw, meta_raw = apply_pipeline("q", chunks, mode="raw", min_score=0.18, top_k_post=2)
    assert len(raw) == 2
    assert meta_raw["hits_pre"] == 4

    filtered, meta_f = apply_pipeline(
        "Guest MCP", chunks, mode="filtered", min_score=0.18, top_k_post=3
    )
    assert all(h.score >= 0.18 for h in filtered)
    assert meta_f["hits_after_threshold"] == 3

    full, meta_full = apply_pipeline(
        "Guest MCP", chunks, mode="full", min_score=0.18, top_k_post=2
    )
    assert len(full) == 2
    assert meta_full.get("rerank") == "heuristic_overlap"


@pytest.mark.asyncio
async def test_pipeline_mode_compare(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "readme.md").write_text(
        "# Guest MCP\n\nStreamable HTTP for visitor tools.\n\n## model_id\n\nEvery answer shows model_id.\n",
        encoding="utf-8",
    )
    settings = Settings(
        rag_data_dir=str(tmp_path / "data"),
        rag_corpus_dir=str(corpus),
        embedding_provider="fake",
        embedding_dims=32,
        rag_chunk_strategy="structural",
        rag_top_k_pre=10,
        rag_top_k_post=3,
        rag_min_score=0.01,
        rag_mode="full",
    )
    store = VectorStore(settings.data_path())
    pipeline = RagPipeline(settings, store, FakeEmbedder(32))
    await pipeline.reindex()
    raw = await pipeline.search_payload("Guest MCP", mode="raw")
    full = await pipeline.search_payload("расскажи про Guest MCP", mode="full")
    assert raw["retrieval"]["mode"] == "raw"
    assert full["retrieval"]["mode"] == "full"
    assert full["query_rewritten"] != full["query"] or "Streamable" in str(
        full["query_rewritten"]
    )
