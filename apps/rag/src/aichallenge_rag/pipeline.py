"""Index corpus + user docs; search."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from aichallenge_rag.chunking import Chunk, chunk_document
from aichallenge_rag.embeddings import Embedder
from aichallenge_rag.settings import Settings
from aichallenge_rag.store import SearchHit, VectorStore, chunk_to_dict

logger = logging.getLogger(__name__)

TEXT_SUFFIXES = {".md", ".txt", ".rst", ".py", ".ts", ".tsx", ".yml", ".yaml", ".toml", ".json"}


def extract_text(path: Path, raw: bytes | None = None) -> str:
    data = raw if raw is not None else path.read_bytes()
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(data))
            return "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except ImportError:
            return data.decode("utf-8", errors="ignore")
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
        chunks = chunk_document(
            text,
            source=source,
            title=title,
            strategy=strategy,
            fixed_size=self.settings.rag_fixed_size,
            fixed_overlap=self.settings.rag_fixed_overlap,
        )
        if not chunks:
            return {"added_chunks": 0, "strategy": strategy}
        vectors = await self.embedder.embed([c.text for c in chunks])
        # Merge with existing rows then rebuild matrix for all ids.
        for chunk, vec in zip(chunks, vectors, strict=True):
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
        return {
            "added_chunks": len(chunks),
            "strategy": strategy,
            "chunk_ids": [c.chunk_id for c in chunks],
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
        # Clear only this strategy+scope then insert; keep other strategies for comparison.
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

    async def _rebuild_all_vectors(self) -> None:
        rows = self.store.list_chunks()
        if not rows:
            self.store.set_matrix([], np.zeros((0, 1), dtype=np.float32), embed_model=self.embedder.model_id)
            return
        texts = [r.text for r in rows]
        # Batch to avoid huge payloads.
        vectors: list[list[float]] = []
        batch = 32
        for i in range(0, len(texts), batch):
            vectors.extend(await self.embedder.embed(texts[i : i + batch]))
        matrix = np.asarray(vectors, dtype=np.float32)
        # L2-normalize rows for cosine via dot.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        matrix = matrix / norms
        self.store.set_matrix(
            [r.chunk_id for r in rows],
            matrix,
            embed_model=self.embedder.model_id,
        )

    async def search(self, query: str, *, top_k: int | None = None) -> list[SearchHit]:
        q = query.strip()
        if not q:
            return []
        vectors = await self.embedder.embed([q])
        return self.store.search(vectors[0], top_k=top_k or self.settings.rag_top_k)

    async def search_payload(self, query: str, *, top_k: int | None = None) -> dict[str, object]:
        hits = await self.search(query, top_k=top_k)
        return {
            "query": query,
            "hits": [chunk_to_dict(h.chunk, h.score) for h in hits],
            "embed_model": self.embedder.model_id,
        }
