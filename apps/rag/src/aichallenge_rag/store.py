"""Qdrant-backed vector store (embedded path or remote URL)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from aichallenge_rag.chunking import Chunk

logger = logging.getLogger(__name__)

_POINT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


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


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(_POINT_NS, chunk_id))


def _payload_from_chunk(
    chunk: Chunk | StoredChunk,
    *,
    scope: str,
    owner_id: str,
    embed_model: str,
) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "source": chunk.source,
        "title": chunk.title,
        "section": chunk.section,
        "strategy": chunk.strategy,
        "index": int(chunk.index),
        "scope": scope,
        "owner_id": owner_id,
        "embed_model": embed_model,
    }


def _chunk_from_payload(payload: dict[str, Any]) -> StoredChunk:
    return StoredChunk(
        chunk_id=str(payload.get("chunk_id") or ""),
        text=str(payload.get("text") or ""),
        source=str(payload.get("source") or ""),
        title=str(payload.get("title") or ""),
        section=str(payload.get("section") or ""),
        strategy=str(payload.get("strategy") or ""),
        index=int(payload.get("index") or 0),
        scope=str(payload.get("scope") or "stand"),
        owner_id=str(payload.get("owner_id") or ""),
    )


class VectorStore:
    """Dense vector index in Qdrant + payload metadata."""

    backend = "qdrant"

    def __init__(
        self,
        data_dir: Path,
        *,
        qdrant_url: str = "",
        collection: str = "aichallenge_rag",
    ) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.collection = collection or "aichallenge_rag"
        self.meta_path = self.data_dir / "index_meta.json"
        self.qdrant_path = self.data_dir / "qdrant"
        self._url = (qdrant_url or "").strip()
        if self._url:
            self._client = QdrantClient(url=self._url)
            logger.info("qdrant remote url=%s collection=%s", self._url, self.collection)
        else:
            self.qdrant_path.mkdir(parents=True, exist_ok=True)
            self._client = QdrantClient(path=str(self.qdrant_path))
            logger.info("qdrant embedded path=%s collection=%s", self.qdrant_path, self.collection)
        self._dims: int | None = self._read_meta_dims()

    def _read_meta(self) -> dict[str, Any]:
        if not self.meta_path.exists():
            return {}
        try:
            return json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _read_meta_dims(self) -> int | None:
        meta = self._read_meta()
        dims = meta.get("dims")
        return int(dims) if dims else None

    def _write_meta(self, *, embed_model: str, dims: int, count: int) -> None:
        payload = {
            "embed_model": embed_model,
            "dims": dims,
            "count": count,
            "backend": "qdrant",
            "collection": self.collection,
        }
        self.meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._dims = dims

    def _collection_exists(self) -> bool:
        try:
            return self._client.collection_exists(self.collection)
        except Exception:
            names = {c.name for c in self._client.get_collections().collections}
            return self.collection in names

    def _ensure_collection(self, dims: int) -> None:
        if dims <= 0:
            raise ValueError("vector dims must be positive")
        if self._collection_exists():
            info = self._client.get_collection(self.collection)
            current = None
            vectors = info.config.params.vectors
            if isinstance(vectors, VectorParams):
                current = int(vectors.size)
            elif isinstance(vectors, dict) and "" in vectors:
                current = int(vectors[""].size)
            elif hasattr(vectors, "size"):
                current = int(vectors.size)  # type: ignore[arg-type]
            if current is not None and current != dims:
                logger.warning(
                    "qdrant dim mismatch collection=%s have=%s need=%s — recreating",
                    self.collection,
                    current,
                    dims,
                )
                self._client.delete_collection(self.collection)
            else:
                self._dims = dims
                return
        self._client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=dims, distance=Distance.COSINE),
        )
        # Payload indexes only help on server Qdrant (noop / warning on embedded).
        if self._url:
            for field in ("scope", "owner_id", "strategy", "source", "chunk_id"):
                try:
                    self._client.create_payload_index(
                        collection_name=self.collection,
                        field_name=field,
                        field_schema="keyword",
                    )
                except Exception:
                    logger.debug(
                        "payload index %s already present or unsupported", field, exc_info=True
                    )
        self._dims = dims

    def compatible(self, *, embed_model: str, dims: int) -> bool:
        """True when new vectors can upsert into the existing collection."""
        if not self._collection_exists():
            return True
        meta = self._read_meta()
        meta_model = str(meta.get("embed_model") or "")
        meta_dims = meta.get("dims")
        if meta_dims is not None and int(meta_dims) != dims:
            return False
        if meta_model and meta_model != embed_model:
            return False
        if self._dims is not None and self._dims != dims:
            return False
        return True

    # Back-compat name used by older pipeline call sites.
    def can_append(self, *, embed_model: str, dims: int) -> bool:
        return self.compatible(embed_model=embed_model, dims=dims)

    def clear(self, *, strategy: str | None = None, scope: str | None = None) -> None:
        if not self._collection_exists():
            return
        if strategy is None and scope is None:
            self._client.delete_collection(self.collection)
            if self.meta_path.exists():
                self.meta_path.unlink()
            self._dims = None
            return
        must: list[FieldCondition] = []
        if strategy is not None:
            must.append(FieldCondition(key="strategy", match=MatchValue(value=strategy)))
        if scope is not None:
            must.append(FieldCondition(key="scope", match=MatchValue(value=scope)))
        self._client.delete(
            collection_name=self.collection,
            points_selector=Filter(must=must),
        )

    def upsert(
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
        if not chunks:
            return 0
        dims = len(vectors[0])
        self._ensure_collection(dims)
        points = [
            PointStruct(
                id=_point_id(chunk.chunk_id),
                vector=[float(x) for x in vec],
                payload=_payload_from_chunk(
                    chunk, scope=scope, owner_id=owner_id, embed_model=embed_model
                ),
            )
            for chunk, vec in zip(chunks, vectors, strict=True)
        ]
        self._client.upsert(collection_name=self.collection, points=points)
        count = self._count()
        self._write_meta(embed_model=embed_model, dims=dims, count=count)
        return len(points)

    def upsert_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
        *,
        scope: str,
        owner_id: str,
        embed_model: str,
    ) -> int:
        return self.upsert(
            chunks, vectors, scope=scope, owner_id=owner_id, embed_model=embed_model
        )

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
        self.clear(strategy=strategy, scope=scope)
        return self.upsert(
            chunks, vectors, scope=scope, owner_id=owner_id, embed_model=embed_model
        )

    def _count(self) -> int:
        if not self._collection_exists():
            return 0
        return int(self._client.count(collection_name=self.collection, exact=True).count)

    def _scroll_all(self, *, batch: int = 256) -> list[Any]:
        if not self._collection_exists():
            return []
        out: list[Any] = []
        offset = None
        while True:
            points, offset = self._client.scroll(
                collection_name=self.collection,
                limit=batch,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            out.extend(points)
            if offset is None:
                break
        return out

    def get_chunk(self, chunk_id: str) -> StoredChunk | None:
        if not self._collection_exists():
            return None
        points = self._client.retrieve(
            collection_name=self.collection,
            ids=[_point_id(chunk_id)],
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return None
        payload = points[0].payload or {}
        return _chunk_from_payload(payload)

    def list_chunks(self) -> list[StoredChunk]:
        chunks = [_chunk_from_payload(p.payload or {}) for p in self._scroll_all()]
        chunks.sort(key=lambda c: (c.source, c.index))
        return chunks

    def delete_document(
        self,
        *,
        source: str,
        scope: str,
        owner_id: str,
    ) -> dict[str, object]:
        if not self._collection_exists():
            return {"deleted_chunks": 0, "source": source, "scope": scope, "owner_id": owner_id}
        # Collect ids for response, then delete by filter.
        filt = Filter(
            must=[
                FieldCondition(key="source", match=MatchValue(value=source)),
                FieldCondition(key="scope", match=MatchValue(value=scope)),
                FieldCondition(key="owner_id", match=MatchValue(value=owner_id)),
            ]
        )
        ids: list[str] = []
        offset = None
        while True:
            points, offset = self._client.scroll(
                collection_name=self.collection,
                scroll_filter=filt,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for p in points:
                payload = p.payload or {}
                ids.append(str(payload.get("chunk_id") or ""))
            if offset is None:
                break
        if not ids:
            return {"deleted_chunks": 0, "source": source, "scope": scope, "owner_id": owner_id}
        self._client.delete(collection_name=self.collection, points_selector=filt)
        meta = self._read_meta()
        self._write_meta(
            embed_model=str(meta.get("embed_model") or "unknown"),
            dims=int(meta.get("dims") or self._dims or 1),
            count=self._count(),
        )
        return {
            "deleted_chunks": len(ids),
            "source": source,
            "scope": scope,
            "owner_id": owner_id,
            "chunk_ids": ids,
        }

    def list_documents(
        self,
        *,
        owner_id: str | None = None,
        include_stand: bool = False,
        all_owners: bool = False,
    ) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str, str], dict[str, object]] = {}
        for chunk in self.list_chunks():
            scope = chunk.scope or "stand"
            oid = chunk.owner_id or ""
            if all_owners:
                pass
            elif include_stand and scope == "stand":
                pass
            elif owner_id is not None and scope == "session" and oid == owner_id:
                pass
            else:
                continue
            key = (chunk.source, scope, oid)
            entry = grouped.get(key)
            if entry is None:
                grouped[key] = {
                    "source": chunk.source,
                    "title": chunk.title or chunk.source,
                    "scope": scope,
                    "owner_id": oid,
                    "strategy": chunk.strategy,
                    "chunk_count": 1,
                    "preview": (chunk.text or "")[:300],
                }
            else:
                entry["chunk_count"] = int(entry["chunk_count"]) + 1
        return list(grouped.values())

    def chunk_visible(self, chunk: StoredChunk, *, owner_id: str | None) -> bool:
        if chunk.scope == "stand":
            return True
        if chunk.scope == "session":
            return bool(owner_id) and chunk.owner_id == owner_id
        return False

    def _owner_filter(self, owner_id: str | None) -> Filter | None:
        """Stand always visible; session only for matching owner."""
        stand = FieldCondition(key="scope", match=MatchValue(value="stand"))
        if not owner_id:
            return Filter(must=[stand])
        session = Filter(
            must=[
                FieldCondition(key="scope", match=MatchValue(value="session")),
                FieldCondition(key="owner_id", match=MatchValue(value=owner_id)),
            ]
        )
        return Filter(should=[Filter(must=[stand]), session])

    def stats(self) -> dict[str, object]:
        chunks = self.list_chunks()
        by_strategy: dict[str, dict[str, float | int]] = {}
        for chunk in chunks:
            bucket = by_strategy.setdefault(chunk.strategy, {"count": 0, "chars": 0.0})
            bucket["count"] = int(bucket["count"]) + 1
            bucket["chars"] = float(bucket["chars"]) + len(chunk.text or "")
        formatted = {
            name: {
                "count": int(vals["count"]),
                "avg_chars": round(float(vals["chars"]) / int(vals["count"]), 1)
                if int(vals["count"])
                else 0.0,
            }
            for name, vals in by_strategy.items()
        }
        meta = self._read_meta()
        vector_count = self._count()
        return {
            "total_chunks": len(chunks),
            "by_strategy": formatted,
            "embed_model": meta.get("embed_model"),
            "vector_count": vector_count,
            "backend": "qdrant",
            "dims": meta.get("dims") or self._dims,
            "collection": self.collection,
        }

    def search(
        self,
        query_vec: list[float],
        *,
        top_k: int = 6,
        owner_id: str | None = None,
    ) -> list[SearchHit]:
        if not self._collection_exists() or top_k <= 0:
            return []
        dims = self._dims or self._read_meta_dims() or len(query_vec)
        q = [float(x) for x in query_vec]
        if len(q) < dims:
            q = q + [0.0] * (dims - len(q))
        elif len(q) > dims:
            q = q[:dims]
        # Over-fetch then rely on server-side filter for ownership.
        limit = min(max(top_k * 4, top_k), 64)
        try:
            response = self._client.query_points(
                collection_name=self.collection,
                query=q,
                query_filter=self._owner_filter(owner_id),
                limit=limit,
                with_payload=True,
            )
        except UnexpectedResponse:
            logger.exception("qdrant search failed")
            return []
        hits: list[SearchHit] = []
        for point in response.points:
            payload = point.payload or {}
            chunk = _chunk_from_payload(payload)
            if not self.chunk_visible(chunk, owner_id=owner_id):
                continue
            # Cosine distance in Qdrant is returned as similarity score for COSINE.
            hits.append(SearchHit(chunk=chunk, score=float(point.score or 0.0)))
            if len(hits) >= top_k:
                break
        return hits

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()


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
