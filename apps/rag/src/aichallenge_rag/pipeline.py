"""Index corpus + user docs; search."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import numpy as np

from aichallenge_rag.chunking import Chunk, chunk_document
from aichallenge_rag.embeddings import Embedder, FakeEmbedder
from aichallenge_rag.rerank import apply_pipeline, rewrite_query
from aichallenge_rag.settings import Settings
from aichallenge_rag.store import SearchHit, VectorStore, chunk_to_dict

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".py", ".ts", ".tsx", ".yml", ".yaml", ".toml", ".json"}

#: Per-batch ceiling for upstream embeddings (API hang fuse).
EMBED_BATCH_TIMEOUT_S = 35.0
#: Whole rebuild/heal budget — then fall back to FakeEmbedder.
REBUILD_BUDGET_S = 90.0


def looks_like_pdf_garbage(text: str) -> bool:
    """True when upload fell back to raw PDF bytes instead of extracted text."""
    head = (text or "")[:800].lstrip()
    if head.startswith("%PDF"):
        return True
    markers = ("endobj", "stream", "/Type /Page", "/BaseFont", "ReportLab Generated")
    hits = sum(1 for m in markers if m in head)
    return hits >= 2


def extract_text(path: Path, raw: bytes | None = None) -> str:
    data = raw if raw is not None else path.read_bytes()
    suffix = path.suffix.lower()
    is_pdf = suffix == ".pdf" or data[:5] == b"%PDF-"
    if is_pdf:
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except ImportError:
            logger.error("pypdf is not installed — cannot extract PDF text")
            return ""
        except Exception:
            logger.exception("PDF extract failed for %s", path.name)
            return ""
        text = text.strip()
        if not text or looks_like_pdf_garbage(text):
            return ""
        return text
    return data.decode("utf-8", errors="ignore")


def iter_corpus_files(corpus_dir: Path) -> list[Path]:
    if not corpus_dir.is_dir():
        return []
    files: list[Path] = []
    for path in sorted(corpus_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES or path.suffix.lower() == ".pdf":
            # Skip huge locks / binaries by size.
            if path.stat().st_size > 2_000_000:
                continue
            files.append(path)
    return files


def _normalize_matrix(vectors: list[list[float]]) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class RagPipeline:
    def __init__(self, settings: Settings, store: VectorStore, embedder: Embedder) -> None:
        self.settings = settings
        self.store = store
        self.embedder = embedder

    async def reindex(
        self,
        *,
        strategy: str | None = None,
        corpus_dir: Path | None = None,
    ) -> dict[str, object]:
        strategy = strategy or self.settings.rag_chunk_strategy
        root = corpus_dir or self.settings.corpus_path()
        files = iter_corpus_files(root)
        chunks: list[Chunk] = []
        for path in files:
            try:
                text = extract_text(path)
            except OSError:
                logger.warning("skip unreadable %s", path)
                continue
            if not text.strip():
                continue
            rel = str(path.relative_to(root)) if path.is_relative_to(root) else path.name
            chunks.extend(
                chunk_document(
                    text,
                    source=rel,
                    title=path.stem,
                    strategy=strategy,
                    fixed_size=self.settings.rag_fixed_size,
                    fixed_overlap=self.settings.rag_fixed_overlap,
                )
            )
        return await self._persist(chunks, strategy=strategy, scope="stand", owner_id="")

    async def add_document(
        self,
        *,
        text: str,
        source: str,
        title: str,
        strategy: str | None = None,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]:
        strategy = strategy or self.settings.rag_chunk_strategy
        if looks_like_pdf_garbage(text):
            return {
                "added_chunks": 0,
                "strategy": strategy,
                "filename": source,
                "title": title,
                "preview": "",
                "chunk_ids": [],
                "scope": scope,
                "owner_id": owner_id,
                "error": "pdf_text_extract_failed",
            }
        chunks = chunk_document(
            text,
            source=source,
            title=title,
            strategy=strategy,
            fixed_size=self.settings.rag_fixed_size,
            fixed_overlap=self.settings.rag_fixed_overlap,
        )
        if not chunks:
            return {
                "added_chunks": 0,
                "strategy": strategy,
                "filename": source,
                "title": title,
                "preview": "",
                "chunk_ids": [],
                "scope": scope,
                "owner_id": owner_id,
            }
        for chunk in chunks:
            self.store._conn.execute(
                """
                INSERT OR REPLACE INTO chunks
                (chunk_id, text, source, title, section, strategy, idx, scope, owner_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.text,
                    chunk.source,
                    chunk.title,
                    chunk.section,
                    chunk.strategy,
                    chunk.index,
                    scope,
                    owner_id,
                ),
            )
        self.store._conn.commit()

        # Prefer embedding only the new rows — full rebuild hangs for hundreds of chunks.
        try:
            vectors = await asyncio.wait_for(
                self.embedder.embed([c.text for c in chunks]),
                timeout=EMBED_BATCH_TIMEOUT_S,
            )
            matrix = _normalize_matrix(vectors)
            dims = int(matrix.shape[1])
            if self.store.can_append(embed_model=self.embedder.model_id, dims=dims):
                self.store.upsert_matrix_rows(
                    [c.chunk_id for c in chunks],
                    matrix,
                    embed_model=self.embedder.model_id,
                )
            else:
                await self._rebuild_all_vectors()
        except Exception:
            logger.exception("add_document embed failed; rebuilding with fallback")
            await self._rebuild_all_vectors()

        preview = (chunks[0].text or "")[:300]
        return {
            "added_chunks": len(chunks),
            "strategy": strategy,
            "chunk_ids": [c.chunk_id for c in chunks],
            "filename": source,
            "title": title,
            "preview": preview,
            "scope": scope,
            "owner_id": owner_id,
        }

    async def _persist(
        self,
        chunks: list[Chunk],
        *,
        strategy: str,
        scope: str,
        owner_id: str,
    ) -> dict[str, object]:
        self.store.clear(strategy=strategy, scope=scope)
        if not chunks:
            await self._rebuild_all_vectors()
            return {"indexed_files": 0, "chunks": 0, "strategy": strategy}
        for chunk in chunks:
            self.store._conn.execute(
                """
                INSERT OR REPLACE INTO chunks
                (chunk_id, text, source, title, section, strategy, idx, scope, owner_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.chunk_id,
                    chunk.text,
                    chunk.source,
                    chunk.title,
                    chunk.section,
                    chunk.strategy,
                    chunk.index,
                    scope,
                    owner_id,
                ),
            )
        self.store._conn.commit()
        await self._rebuild_all_vectors()
        sources = {c.source for c in chunks}
        return {
            "indexed_files": len(sources),
            "chunks": len(chunks),
            "strategy": strategy,
            "avg_chars": round(sum(len(c.text) for c in chunks) / len(chunks), 1),
        }

    async def _embed_texts(self, texts: list[str], *, batch: int = 32) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), batch):
            part = texts[i : i + batch]
            vectors.extend(
                await asyncio.wait_for(self.embedder.embed(part), timeout=EMBED_BATCH_TIMEOUT_S)
            )
        return vectors

    async def _rebuild_all_vectors(self) -> None:
        rows = self.store.list_chunks()
        if not rows:
            self.store.set_matrix(
                [], np.zeros((0, 1), dtype=np.float32), embed_model=self.embedder.model_id
            )
            return
        texts = [r.text for r in rows]

        async def _run() -> list[list[float]]:
            return await self._embed_texts(texts)

        try:
            vectors = await asyncio.wait_for(_run(), timeout=REBUILD_BUDGET_S)
        except Exception:
            logger.exception(
                "embed rebuild failed/timed out; falling back to FakeEmbedder (%s chunks)",
                len(texts),
            )
            fake = FakeEmbedder(getattr(self.settings, "embedding_dims", 64) or 64)
            self.embedder = fake
            vectors = await self._embed_texts(texts)

        matrix = _normalize_matrix(vectors)
        self.store.set_matrix(
            [r.chunk_id for r in rows],
            matrix,
            embed_model=self.embedder.model_id,
        )

    async def ensure_vectors(self) -> dict[str, object]:
        """Rebuild matrix when chunks exist but vectors are missing (prod heal)."""
        stats = self.store.stats()
        total = int(stats.get("total_chunks") or 0)
        vectors = int(stats.get("vector_count") or 0)
        if total == 0:
            result = await self.reindex(strategy="structural")
            await self.reindex(strategy="fixed")
            return {"healed": "indexed_both", **result}
        if vectors > 0 and vectors == total:
            return {"healed": False, "total_chunks": total, "vector_count": vectors}
        await self._rebuild_all_vectors()
        after = self.store.stats()
        return {
            "healed": True,
            "total_chunks": after.get("total_chunks"),
            "vector_count": after.get("vector_count"),
            "embed_model": after.get("embed_model"),
        }

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        mode: str | None = None,
        top_k_pre: int | None = None,
        top_k_post: int | None = None,
        min_score: float | None = None,
        owner_id: str | None = None,
    ) -> list[SearchHit]:
        q = query.strip()
        if not q:
            return []
        mode_eff = (mode or self.settings.rag_mode or "full").strip().lower()
        if mode_eff not in {"raw", "filtered", "full"}:
            mode_eff = "full"
        rewritten = rewrite_query(q) if mode_eff == "full" else q
        pre = top_k_pre or self.settings.rag_top_k_pre
        post = top_k_post or top_k or self.settings.rag_top_k_post or self.settings.rag_top_k
        threshold = self.settings.rag_min_score if min_score is None else min_score
        try:
            vectors = await self._embed_query([rewritten])
        except Exception:
            logger.exception("query embed failed")
            return []
        raw_hits = self.store.search(vectors[0], top_k=pre, owner_id=owner_id)
        final_hits, _meta = apply_pipeline(
            rewritten,
            raw_hits,
            mode=mode_eff,
            min_score=threshold,
            top_k_post=post,
        )
        return final_hits

    def list_documents(
        self,
        *,
        owner_id: str | None = None,
        include_stand: bool = False,
        all_owners: bool = False,
    ) -> dict[str, object]:
        docs = self.store.list_documents(
            owner_id=owner_id,
            include_stand=include_stand,
            all_owners=all_owners,
        )
        return {"documents": docs, "count": len(docs)}

    async def _embed_query(self, texts: list[str]) -> list[list[float]]:
        """Embed query; keep the same space as the on-disk matrix when possible."""
        stats = self.store.stats()
        matrix_model = str(stats.get("embed_model") or "")
        # Healed indexes often sit on fake-hash while runtime provider is still API.
        if matrix_model == "fake-hash" and self.embedder.model_id != "fake-hash":
            fake = FakeEmbedder(getattr(self.settings, "embedding_dims", 64) or 64)
            self.embedder = fake
            return await fake.embed(texts)
        try:
            return await asyncio.wait_for(
                self.embedder.embed(texts),
                timeout=min(EMBED_BATCH_TIMEOUT_S, 12.0),
            )
        except Exception:
            logger.warning("query embed failed/timed out; using FakeEmbedder for search")
            fake = FakeEmbedder(getattr(self.settings, "embedding_dims", 64) or 64)
            self.embedder = fake
            return await fake.embed(texts)

    async def search_payload(
        self,
        query: str,
        *,
        top_k: int | None = None,
        mode: str | None = None,
        top_k_pre: int | None = None,
        top_k_post: int | None = None,
        min_score: float | None = None,
        owner_id: str | None = None,
    ) -> dict[str, object]:
        q = query.strip()
        if not q:
            return {
                "query": query,
                "query_rewritten": query,
                "hits": [],
                "embed_model": self.embedder.model_id,
                "retrieval": {"mode": mode or self.settings.rag_mode, "hits_pre": 0, "hits_post": 0},
            }

        mode_eff = (mode or self.settings.rag_mode or "full").strip().lower()
        if mode_eff not in {"raw", "filtered", "full"}:
            mode_eff = "full"

        rewritten = rewrite_query(q) if mode_eff == "full" else q
        pre = top_k_pre or self.settings.rag_top_k_pre
        post = top_k_post or top_k or self.settings.rag_top_k_post or self.settings.rag_top_k
        threshold = self.settings.rag_min_score if min_score is None else min_score

        try:
            vectors = await self._embed_query([rewritten])
        except Exception:
            logger.exception("query embed failed")
            return {
                "query": q,
                "query_rewritten": rewritten,
                "hits": [],
                "embed_model": self.embedder.model_id,
                "retrieval": {
                    "mode": mode_eff,
                    "hits_pre": 0,
                    "hits_post": 0,
                    "error": "embed_timeout",
                },
            }
        raw_hits = self.store.search(vectors[0], top_k=pre, owner_id=owner_id)
        final_hits, retrieval_meta = apply_pipeline(
            rewritten,
            raw_hits,
            mode=mode_eff,
            min_score=threshold,
            top_k_post=post,
        )
        return {
            "query": q,
            "query_rewritten": rewritten,
            "hits": [chunk_to_dict(h.chunk, h.score) for h in final_hits],
            "embed_model": self.embedder.model_id,
            "retrieval": retrieval_meta,
        }
