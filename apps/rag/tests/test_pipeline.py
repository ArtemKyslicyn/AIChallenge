"""Pipeline heal + Qdrant upsert indexing."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aichallenge_rag.embeddings import FakeEmbedder
from aichallenge_rag.pipeline import EMBED_BATCH_TIMEOUT_S, RagPipeline
from aichallenge_rag.settings import Settings
from aichallenge_rag.store import VectorStore


class _HangingEmbedder:
    """Never returns — used to assert wait_for / Fake fallback."""

    model_id = "hang"
    dims = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        await asyncio.sleep(3600)
        return [[0.0] * self.dims for _ in texts]


@pytest.mark.asyncio
async def test_ensure_vectors_indexes_empty_store_from_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("# Hello\n\nguest mcp docs here.\n", encoding="utf-8")
    settings = Settings(
        rag_data_dir=str(tmp_path / "data"),
        rag_corpus_dir=str(corpus),
        embedding_provider="fake",
        embedding_dims=16,
    )
    store = VectorStore(settings.data_path())
    assert store.stats()["total_chunks"] == 0

    pipe = RagPipeline(settings, store, FakeEmbedder(16))
    result = await pipe.ensure_vectors()
    assert result["healed"] in {True, "indexed_both"} or result.get("healed")
    assert int(store.stats()["vector_count"] or 0) >= 1
    hits = await pipe.search("guest mcp", top_k=3, mode="raw")
    assert hits
    store.close()


@pytest.mark.asyncio
async def test_add_document_upserts_without_losing_previous(tmp_path: Path) -> None:
    settings = Settings(
        rag_data_dir=str(tmp_path),
        embedding_provider="fake",
        embedding_dims=16,
    )
    store = VectorStore(tmp_path)
    pipe = RagPipeline(settings, store, FakeEmbedder(16))
    first = await pipe.add_document(
        text="# One\n\nAlpha content about models.",
        source="one.md",
        title="one",
        strategy="structural",
    )
    assert int(first["added_chunks"] or 0) >= 1
    n1 = int(store.stats()["vector_count"] or 0)
    second = await pipe.add_document(
        text="# Two\n\nBeta content about sessions.",
        source="two.md",
        title="two",
        strategy="structural",
    )
    assert int(second["added_chunks"] or 0) >= 1
    n2 = int(store.stats()["vector_count"] or 0)
    assert n2 > n1
    store.close()


@pytest.mark.asyncio
async def test_list_documents_and_search_owner_filter(tmp_path: Path) -> None:
    settings = Settings(
        rag_data_dir=str(tmp_path),
        embedding_provider="fake",
        embedding_dims=16,
    )
    store = VectorStore(tmp_path)
    pipe = RagPipeline(settings, store, FakeEmbedder(16))
    await pipe.add_document(
        text="# Stand\n\nPublic stand corpus about Reality ports.",
        source="stand.md",
        title="stand",
        strategy="structural",
        scope="stand",
        owner_id="",
    )
    await pipe.add_document(
        text="# Mine\n\nPrivate notes about my orange widget.",
        source="mine.md",
        title="mine",
        strategy="structural",
        scope="session",
        owner_id="user-a",
    )
    await pipe.add_document(
        text="# Other\n\nSecret other-user document about purple widget.",
        source="other.md",
        title="other",
        strategy="structural",
        scope="session",
        owner_id="user-b",
    )
    mine = pipe.list_documents(owner_id="user-a", all_owners=False)
    assert mine["count"] == 1
    assert mine["documents"][0]["source"] == "mine.md"  # type: ignore[index]
    admin = pipe.list_documents(all_owners=True)
    assert int(admin["count"] or 0) >= 3
    hits_a = await pipe.search("purple widget", top_k=5, mode="raw", owner_id="user-a")
    sources_a = {h.chunk.source for h in hits_a}
    assert "other.md" not in sources_a
    hits_b = await pipe.search("purple widget", top_k=5, mode="raw", owner_id="user-b")
    sources_b = {h.chunk.source for h in hits_b}
    assert "other.md" in sources_b or any("purple" in h.chunk.text.lower() for h in hits_b)
    deleted = pipe.delete_document(source="mine.md", scope="session", owner_id="user-a")
    assert int(deleted["deleted_chunks"] or 0) >= 1
    mine_after = pipe.list_documents(owner_id="user-a", all_owners=False)
    assert mine_after["count"] == 0
    store.close()


@pytest.mark.asyncio
async def test_rebuild_falls_back_when_embedder_hangs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("aichallenge_rag.pipeline.EMBED_BATCH_TIMEOUT_S", 0.05)
    monkeypatch.setattr("aichallenge_rag.pipeline.REBUILD_BUDGET_S", 0.15)

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.md").write_text("# Hang\n\nhang probe text\n", encoding="utf-8")
    settings = Settings(
        rag_data_dir=str(tmp_path / "data"),
        rag_corpus_dir=str(corpus),
        embedding_provider="fake",
        embedding_dims=8,
    )
    store = VectorStore(settings.data_path())
    pipe = RagPipeline(settings, store, _HangingEmbedder())  # type: ignore[arg-type]
    result = await pipe.reindex(strategy="structural")
    assert int(result["chunks"] or 0) >= 1
    assert pipe.embedder.model_id == "fake-hash"
    assert int(store.stats()["vector_count"] or 0) >= 1
    assert EMBED_BATCH_TIMEOUT_S > 0
    store.close()


@pytest.mark.asyncio
async def test_qdrant_search_uses_vector_store(tmp_path: Path) -> None:
    """Smoke: Qdrant-backed store returns scored hits (not numpy matrix)."""
    settings = Settings(
        rag_data_dir=str(tmp_path),
        embedding_provider="fake",
        embedding_dims=16,
    )
    store = VectorStore(tmp_path)
    assert (tmp_path / "qdrant").exists() or store.backend == "qdrant"
    pipe = RagPipeline(settings, store, FakeEmbedder(16))
    await pipe.add_document(
        text="# Qdrant\n\nVector search with HNSW index.",
        source="q.md",
        title="q",
        strategy="structural",
        scope="stand",
    )
    hits = store.search((await FakeEmbedder(16).embed(["HNSW vector"]))[0], top_k=3)
    assert hits
    assert hits[0].chunk.source == "q.md"
    assert isinstance(hits[0].score, float)
    store.close()
