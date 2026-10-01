"""Embedding providers: API, fake (deterministic), optional local."""

from __future__ import annotations

import hashlib
import logging
from typing import Protocol

import httpx
import numpy as np

from aichallenge_rag.settings import Settings

logger = logging.getLogger(__name__)

#: Hard ceilings so a dead upstream cannot hang heal / upload / search.
EMBED_CONNECT_S = 5.0
EMBED_READ_S = 30.0
EMBED_WRITE_S = 30.0
EMBED_POOL_S = 5.0


class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dims(self) -> int: ...

    @property
    def model_id(self) -> str: ...


class FakeEmbedder:
    """Hash → unit vector. For tests and keyless demos."""

    def __init__(self, dims: int = 64) -> None:
        self._dims = dims

    @property
    def dims(self) -> int:
        return self._dims

    @property
    def model_id(self) -> str:
        return "fake-hash"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            raw = np.frombuffer((digest * ((self._dims // 32) + 1))[: self._dims * 4], dtype=np.uint8)
            vec = (raw.astype(np.float32)[: self._dims] / 255.0) - 0.5
            norm = float(np.linalg.norm(vec)) or 1.0
            out.append((vec / norm).tolist())
        return out


class ApiEmbedder:
    def __init__(self, *, base_url: str, api_key: str, model: str) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._model = model
        self._dims: int | None = None
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=EMBED_CONNECT_S,
                read=EMBED_READ_S,
                write=EMBED_WRITE_S,
                pool=EMBED_POOL_S,
            )
        )

    @property
    def dims(self) -> int:
        return self._dims or 1536

    @property
    def model_id(self) -> str:
        return self._model

    async def aclose(self) -> None:
        await self._client.aclose()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self._base}/embeddings"
        resp = await self._client.post(
            url,
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "input": texts},
        )
        resp.raise_for_status()
        data = resp.json()
        items = sorted(data.get("data") or [], key=lambda row: int(row.get("index", 0)))
        vectors = [list(map(float, row["embedding"])) for row in items]
        if vectors:
            self._dims = len(vectors[0])
        return vectors


class LocalEmbedder:
    """Lazy sentence-transformers. Import only when admin enables local."""

    def __init__(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        self._dims: int | None = None

    @property
    def dims(self) -> int:
        return self._dims or 384

    @property
    def model_id(self) -> str:
        return self._model_name

    def _ensure(self) -> None:
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "local embeddings require sentence-transformers (pip install aichallenge-rag[local])"
            ) from exc
        self._model = SentenceTransformer(self._model_name)
        probe = self._model.encode(["ping"], normalize_embeddings=True)
        self._dims = int(probe.shape[1])

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure()
        assert self._model is not None
        vectors = self._model.encode(texts, normalize_embeddings=True)
        return [v.tolist() for v in vectors]


def build_embedder(settings: Settings) -> Embedder:
    kind = settings.effective_provider()
    if kind == "local":
        logger.info("embedder=local model=%s", settings.local_embedding_model)
        return LocalEmbedder(settings.local_embedding_model)
    if kind == "api":
        logger.info("embedder=api model=%s", settings.embedding_model)
        return ApiEmbedder(
            base_url=settings.llm_base_url,
            api_key=settings.effective_api_key(),
            model=settings.embedding_model,
        )
    logger.info("embedder=fake dims=%s", settings.embedding_dims)
    return FakeEmbedder(settings.embedding_dims)
