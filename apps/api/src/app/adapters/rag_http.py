"""HTTP client for the rag compose sidecar."""

from __future__ import annotations

import logging

import httpx

from app.domain.rag import RagChunkHit, RagSearchResult

logger = logging.getLogger(__name__)


class HttpRagClient:
    def __init__(self, base_url: str, token: str = "", *, timeout: float = 60.0) -> None:
        self._base = base_url.rstrip("/")
        self._token = token.strip()
        self._client = httpx.AsyncClient(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        if not self._token:
            return {}
        return {"Authorization": f"Bearer {self._token}"}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def search(self, query: str, *, top_k: int = 6) -> RagSearchResult:
        resp = await self._client.post(
            f"{self._base}/v1/ask",
            headers=self._headers(),
            json={"query": query, "top_k": top_k},
        )
        resp.raise_for_status()
        data = resp.json()
        hits = tuple(
            RagChunkHit(
                chunk_id=str(h.get("chunk_id") or ""),
                text=str(h.get("text") or ""),
                source=str(h.get("source") or ""),
                title=str(h.get("title") or ""),
                section=str(h.get("section") or ""),
                strategy=str(h.get("strategy") or ""),
                score=float(h.get("score") or 0.0),
            )
            for h in (data.get("hits") or [])
            if isinstance(h, dict)
        )
        return RagSearchResult(
            query=str(data.get("query") or query),
            hits=hits,
            context=str(data.get("context") or data.get("prompt_suffix") or ""),
            embed_model=str(data.get("embed_model") or "") or None,
        )

    async def add_document_text(
        self,
        *,
        text: str,
        source: str,
        title: str,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]:
        resp = await self._client.post(
            f"{self._base}/v1/documents",
            headers=self._headers(),
            json={
                "text": text,
                "source": source,
                "title": title,
                "scope": scope,
                "owner_id": owner_id,
            },
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def add_document_bytes(
        self,
        *,
        filename: str,
        data: bytes,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]:
        resp = await self._client.post(
            f"{self._base}/v1/documents/upload",
            headers=self._headers(),
            files={"file": (filename, data)},
            data={"scope": scope, "owner_id": owner_id},
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def stats(self) -> dict[str, object]:
        resp = await self._client.get(f"{self._base}/v1/stats", headers=self._headers())
        resp.raise_for_status()
        return dict(resp.json())

    async def patch_settings(self, payload: dict[str, object]) -> dict[str, object]:
        resp = await self._client.patch(
            f"{self._base}/v1/settings",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return dict(resp.json())

    async def reindex(self, strategy: str | None = None) -> dict[str, object]:
        body: dict[str, object] = {}
        if strategy:
            body["strategy"] = strategy
        resp = await self._client.post(
            f"{self._base}/v1/index",
            headers=self._headers(),
            json=body,
        )
        resp.raise_for_status()
        return dict(resp.json())
