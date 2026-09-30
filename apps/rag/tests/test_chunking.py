"""Unit tests for chunking + in-memory index search."""

from __future__ import annotations

from pathlib import Path

import pytest

from aichallenge_rag.chunking import chunk_document, chunk_fixed, chunk_structural
from aichallenge_rag.embeddings import FakeEmbedder
from aichallenge_rag.pipeline import RagPipeline
from aichallenge_rag.settings import Settings
from aichallenge_rag.store import VectorStore


SAMPLE = """# Title

Intro paragraph about the stand.

## Section A

Details for section A with enough text to matter.

## Section B

Details for section B and Guest MCP notes.
"""


def test_fixed_chunks_have_metadata() -> None:
    chunks = chunk_fixed(SAMPLE, source="docs/a.md", title="a", size=80, overlap=10)
    assert len(chunks) >= 2
    assert all(c.strategy == "fixed" for c in chunks)
    assert all(c.source == "docs/a.md" for c in chunks)
    assert all(c.chunk_id for c in chunks)


def test_structural_chunks_follow_headings() -> None:
    chunks = chunk_structural(SAMPLE, source="docs/a.md", title="a")
    assert len(chunks) >= 2
    sections = {c.section for c in chunks}
    assert "Section A" in sections or any("Section" in s for s in sections)
    assert all(c.strategy == "structural" for c in chunks)


def test_chunk_document_switch() -> None:
    fixed = chunk_document(SAMPLE, source="x", title="x", strategy="fixed", fixed_size=100)
    structural = chunk_document(SAMPLE, source="x", title="x", strategy="structural")
    assert fixed[0].strategy == "fixed"
    assert structural[0].strategy == "structural"


@pytest.mark.asyncio
async def test_pipeline_index_and_search(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "readme.md").write_text(SAMPLE, encoding="utf-8")
    settings = Settings(
        rag_data_dir=str(tmp_path / "data"),
        rag_corpus_dir=str(corpus),
        embedding_provider="fake",
        embedding_dims=32,
        rag_chunk_strategy="structural",
    )
    store = VectorStore(settings.data_path())
    pipeline = RagPipeline(settings, store, FakeEmbedder(32))
    indexed = await pipeline.reindex()
    assert indexed["chunks"] >= 1
    hits = await pipeline.search("Guest MCP")
    assert isinstance(hits, list)
    stats = store.stats()
    assert stats["total_chunks"] >= 1
