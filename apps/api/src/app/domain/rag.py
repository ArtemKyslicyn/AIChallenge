"""RAG port — search/index against the sidecar service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RagChunkHit:
    chunk_id: str
    text: str
    source: str
    title: str
    section: str
    strategy: str
    score: float


@dataclass(frozen=True, slots=True)
class RagSearchResult:
    query: str
    hits: tuple[RagChunkHit, ...]
    context: str
    embed_model: str | None = None
    query_rewritten: str | None = None
    retrieval: dict[str, object] | None = None


class RagClient(Protocol):
    async def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        mode: str | None = None,
        owner_id: str | None = None,
    ) -> RagSearchResult: ...

    async def add_document_text(
        self,
        *,
        text: str,
        source: str,
        title: str,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]: ...

    async def add_document_bytes(
        self,
        *,
        filename: str,
        data: bytes,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]: ...

    async def list_documents(
        self,
        *,
        owner_id: str | None = None,
        include_stand: bool = False,
        all_owners: bool = False,
    ) -> dict[str, object]: ...

    async def delete_document(
        self,
        *,
        source: str,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]: ...

    async def stats(self) -> dict[str, object]: ...

    async def patch_settings(self, payload: dict[str, object]) -> dict[str, object]: ...

    async def reindex(self, strategy: str | None = None) -> dict[str, object]: ...

    async def heal(self) -> dict[str, object]: ...


class NullRagClient:
    """No-op when RAG_BASE_URL is unset."""

    async def search(
        self,
        query: str,
        *,
        top_k: int = 6,
        mode: str | None = None,
        owner_id: str | None = None,
    ) -> RagSearchResult:
        return RagSearchResult(
            query=query,
            hits=(),
            context="",
            embed_model=None,
            query_rewritten=query,
            retrieval={"mode": mode or "raw", "hits_pre": 0, "hits_post": 0},
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
        return {"added_chunks": 0, "disabled": True, "filename": source, "preview": ""}

    async def add_document_bytes(
        self,
        *,
        filename: str,
        data: bytes,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]:
        return {"added_chunks": 0, "disabled": True, "filename": filename, "preview": ""}

    async def list_documents(
        self,
        *,
        owner_id: str | None = None,
        include_stand: bool = False,
        all_owners: bool = False,
    ) -> dict[str, object]:
        return {"documents": [], "count": 0, "disabled": True}

    async def delete_document(
        self,
        *,
        source: str,
        scope: str = "session",
        owner_id: str = "",
    ) -> dict[str, object]:
        return {"deleted_chunks": 0, "disabled": True, "source": source}

    async def stats(self) -> dict[str, object]:
        return {"total_chunks": 0, "disabled": True}

    async def patch_settings(self, payload: dict[str, object]) -> dict[str, object]:
        return {"disabled": True}

    async def reindex(self, strategy: str | None = None) -> dict[str, object]:
        return {"chunks": 0, "disabled": True}

    async def heal(self) -> dict[str, object]:
        return {"healed": False, "disabled": True}


def format_rag_system_context(result: RagSearchResult) -> str:
    if not result.hits:
        return (
            "Режим базы знаний включён, но релевантных фрагментов не найдено. "
            "Ответь честно, без выдуманных цитат."
        )
    lines = [
        "Ниже фрагменты из базы знаний стенда. Опирайся на них в ответе. "
        "Если данных недостаточно — скажи об этом. Укажи источники по title/source."
    ]
    for i, hit in enumerate(result.hits, start=1):
        lines.append(
            f"[{i}] {hit.title} · {hit.section} ({hit.source}) id={hit.chunk_id}\n{hit.text}"
        )
    return "\n\n".join(lines)
