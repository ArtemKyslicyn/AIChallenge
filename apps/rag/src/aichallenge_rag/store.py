"""SQLite metadata + numpy vector matrix on disk."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from aichallenge_rag.chunking import Chunk


@dataclass(slots=True)
class StoredChunk:
    chunk_id: str
    text: str
    source: str
    title: str
    section: str
    strategy: str
    index: int
    scope: str = "stand"
    owner_id: str = ""


@dataclass(slots=True)
class SearchHit:
    chunk: StoredChunk
    score: float


class VectorStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "chunks.sqlite"
        self.vectors_path = self.data_dir / "vectors.npy"
        self.meta_path = self.data_dir / "index_meta.json"
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._vectors: np.ndarray | None = None
        self._ids: list[str] = []
        self._load_vectors()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chunks (
              chunk_id TEXT PRIMARY KEY,
              text TEXT NOT NULL,
              source TEXT NOT NULL,
              title TEXT NOT NULL,
              section TEXT NOT NULL,
              strategy TEXT NOT NULL,
              idx INTEGER NOT NULL,
              scope TEXT NOT NULL DEFAULT 'stand',
              owner_id TEXT NOT NULL DEFAULT ''
            )
            """
        )
        self._conn.commit()

    def _load_vectors(self) -> None:
        if self.vectors_path.exists() and self.meta_path.exists():
            self._vectors = np.load(self.vectors_path)
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            self._ids = list(meta.get("ids") or [])
        else:
            self._vectors = None
            self._ids = []

    def clear(self, *, strategy: str | None = None, scope: str | None = None) -> None:
        if strategy and scope:
            self._conn.execute(
                "DELETE FROM chunks WHERE strategy = ? AND scope = ?", (strategy, scope)
            )
        elif strategy:
            self._conn.execute("DELETE FROM chunks WHERE strategy = ?", (strategy,))
        elif scope:
            self._conn.execute("DELETE FROM chunks WHERE scope = ?", (scope,))
        else:
            self._conn.execute("DELETE FROM chunks")
        self._conn.commit()
        self._vectors = None
        self._ids = []
        for path in (self.vectors_path, self.meta_path):
            if path.exists():
                path.unlink()

    def replace_all(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
        *,
        scope: str = "stand",
        owner_id: str = "",
        strategy: str,
        embed_model: str,
    ) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("chunks/vectors length mismatch")
        self.clear(strategy=strategy, scope=scope)
        for chunk in chunks:
            self._conn.execute(
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
        self._conn.commit()
        return self._rebuild_matrix(embed_model=embed_model)

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
        *,
        scope: str,
        owner_id: str,
        embed_model: str,
    ) -> int:
        if len(chunks) != len(vectors):
            raise ValueError("chunks/vectors length mismatch")
        for chunk in chunks:
            self._conn.execute(
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
        self._conn.commit()
        return self._rebuild_matrix(embed_model=embed_model)

    def _rebuild_matrix(self, *, embed_model: str) -> int:
        rows = self._conn.execute(
            "SELECT chunk_id, text FROM chunks ORDER BY source, idx"
        ).fetchall()
        # Vectors must be re-read from caller path — we keep ids aligned by re-encode outside.
        # Here we only sync ids list if vectors.npy was written by pipeline via set_matrix.
        self._ids = [row["chunk_id"] for row in rows]
        meta = {
            "ids": self._ids,
            "embed_model": embed_model,
            "count": len(self._ids),
        }
        self.meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(self._ids)

    def set_matrix(self, ids: list[str], matrix: np.ndarray, *, embed_model: str) -> None:
        if len(ids) != matrix.shape[0]:
            raise ValueError("ids/matrix mismatch")
        self._ids = list(ids)
        self._vectors = matrix.astype(np.float32)
        np.save(self.vectors_path, self._vectors)
        self.meta_path.write_text(
            json.dumps(
                {"ids": self._ids, "embed_model": embed_model, "count": len(self._ids)},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def get_chunk(self, chunk_id: str) -> StoredChunk | None:
        row = self._conn.execute(
            "SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)
        ).fetchone()
        if row is None:
            return None
        return StoredChunk(
            chunk_id=row["chunk_id"],
            text=row["text"],
            source=row["source"],
            title=row["title"],
            section=row["section"],
            strategy=row["strategy"],
            index=row["idx"],
            scope=row["scope"],
            owner_id=row["owner_id"],
        )

    def list_chunks(self) -> list[StoredChunk]:
        rows = self._conn.execute("SELECT * FROM chunks ORDER BY source, idx").fetchall()
        return [
            StoredChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                source=row["source"],
                title=row["title"],
                section=row["section"],
                strategy=row["strategy"],
                index=row["idx"],
                scope=row["scope"],
                owner_id=row["owner_id"],
            )
            for row in rows
        ]

    def stats(self) -> dict[str, object]:
        rows = self._conn.execute(
            "SELECT strategy, COUNT(*) AS n, AVG(LENGTH(text)) AS avg_len FROM chunks GROUP BY strategy"
        ).fetchall()
        by_strategy = {
            row["strategy"]: {"count": row["n"], "avg_chars": round(float(row["avg_len"] or 0), 1)}
            for row in rows
        }
        total = self._conn.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()["n"]
        meta = {}
        if self.meta_path.exists():
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        return {
            "total_chunks": total,
            "by_strategy": by_strategy,
            "embed_model": meta.get("embed_model"),
            "vector_count": int(self._vectors.shape[0]) if self._vectors is not None else 0,
        }

    def search(self, query_vec: list[float], *, top_k: int = 6) -> list[SearchHit]:
        if self._vectors is None or not self._ids:
            return []
        q = np.asarray(query_vec, dtype=np.float32)
        q_norm = float(np.linalg.norm(q)) or 1.0
        q = q / q_norm
        # Align dims if fake vs api switched — truncate/pad.
        dim = self._vectors.shape[1]
        if q.shape[0] < dim:
            q = np.pad(q, (0, dim - q.shape[0]))
        elif q.shape[0] > dim:
            q = q[:dim]
        scores = self._vectors @ q
        k = min(top_k, len(self._ids))
        if k <= 0:
            return []
        top_idx = np.argpartition(-scores, kth=k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]
        hits: list[SearchHit] = []
        for i in top_idx:
            chunk = self.get_chunk(self._ids[int(i)])
            if chunk is None:
                continue
            hits.append(SearchHit(chunk=chunk, score=float(scores[int(i)])))
        return hits

    def close(self) -> None:
        self._conn.close()


def chunk_to_dict(chunk: StoredChunk | Chunk, score: float | None = None) -> dict[str, object]:
    if isinstance(chunk, Chunk):
        payload = asdict(chunk)
    else:
        payload = {
            "chunk_id": chunk.chunk_id,
            "text": chunk.text,
            "source": chunk.source,
            "title": chunk.title,
            "section": chunk.section,
            "strategy": chunk.strategy,
            "index": chunk.index,
            "scope": chunk.scope,
            "owner_id": chunk.owner_id,
        }
    if score is not None:
        payload["score"] = round(score, 4)
    return payload
