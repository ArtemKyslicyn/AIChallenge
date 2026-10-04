"""FastAPI HTTP surface for index / documents / search / stats / settings."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from aichallenge_rag.embeddings import build_embedder
from aichallenge_rag.pipeline import (
    REBUILD_BUDGET_S,
    RagPipeline,
    extract_text,
    looks_like_pdf_garbage,
)
from aichallenge_rag.settings import Settings, get_settings
from aichallenge_rag.store import VectorStore

logger = logging.getLogger(__name__)

#: Startup heal must not block /health (compose healthcheck).
STARTUP_HEAL_BUDGET_S = REBUILD_BUDGET_S + 30.0


class IndexRequest(BaseModel):
    strategy: str | None = Field(default=None, pattern="^(fixed|structural)$")


class DocumentTextRequest(BaseModel):
    text: str = Field(min_length=1)
    source: str = "upload.txt"
    title: str = "upload"
    strategy: str | None = None
    scope: str = "session"
    owner_id: str = ""


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=32)
    mode: str | None = Field(default=None, pattern="^(raw|filtered|full)$")
    top_k_pre: int | None = Field(default=None, ge=1, le=64)
    top_k_post: int | None = Field(default=None, ge=1, le=32)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)
    owner_id: str | None = None


class SettingsPatch(BaseModel):
    local_embeddings: bool | None = None
    embedding_provider: str | None = Field(default=None, pattern="^(api|local|fake)$")
    chunk_strategy: str | None = Field(default=None, pattern="^(fixed|structural)$")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = VectorStore(settings.data_path())
        embedder = build_embedder(settings)
        pipeline = RagPipeline(settings, store, embedder)
        state["store"] = store
        state["embedder"] = embedder
        state["pipeline"] = pipeline
        state["settings"] = settings
        state["heal_task"] = None

        async def _startup_heal() -> None:
            stats0 = store.stats()
            try:
                async with asyncio.timeout(STARTUP_HEAL_BUDGET_S):
                    if int(stats0.get("total_chunks") or 0) == 0:
                        structural = await pipeline.reindex(strategy="structural")
                        fixed = await pipeline.reindex(strategy="fixed")
                        logger.info("auto-index structural=%s fixed=%s", structural, fixed)
                    elif int(stats0.get("vector_count") or 0) == 0:
                        healed = await pipeline.ensure_vectors()
                        logger.info("auto-heal vectors %s", healed)
                    state["embedder"] = pipeline.embedder
                    state["pipeline"] = pipeline
            except TimeoutError:
                logger.error("auto-index/heal exceeded %ss — serving without wait", STARTUP_HEAL_BUDGET_S)
            except Exception:
                logger.exception("auto-index/heal failed")

        # Background: do not block uvicorn ready / Docker HEALTHCHECK.
        state["heal_task"] = asyncio.create_task(_startup_heal())
        yield
        heal_task = state.get("heal_task")
        if heal_task is not None and not heal_task.done():
            heal_task.cancel()
            try:
                await heal_task
            except asyncio.CancelledError:
                pass
        close = getattr(state.get("embedder"), "aclose", None)
        if close is not None:
            await close()
        store.close()

    app = FastAPI(title="AIChallenge RAG", version="0.1.0", lifespan=lifespan)

    def pipeline() -> RagPipeline:
        return state["pipeline"]

    def cfg() -> Settings:
        return state["settings"]

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/stats")
    async def stats() -> dict[str, Any]:
        s = cfg()
        return {
            **state["store"].stats(),
            "embedding_provider": s.effective_provider(),
            "local_embeddings_enabled": s.local_embeddings_enabled,
            "chunk_strategy": s.rag_chunk_strategy,
            "embed_model_runtime": state["embedder"].model_id,
        }

    @app.post("/v1/index")
    async def index(body: IndexRequest) -> dict[str, Any]:
        return await pipeline().reindex(strategy=body.strategy)

    @app.post("/v1/heal")
    async def heal() -> dict[str, Any]:
        """Rebuild embeddings if chunks exist without a vector matrix."""
        result = await pipeline().ensure_vectors()
        state["embedder"] = state["pipeline"].embedder
        return {**result, **(await stats())}

    @app.post("/v1/documents")
    async def add_document_json(body: DocumentTextRequest) -> dict[str, Any]:
        return await pipeline().add_document(
            text=body.text,
            source=body.source,
            title=body.title,
            strategy=body.strategy,
            scope=body.scope,
            owner_id=body.owner_id,
        )

    @app.post("/v1/documents/upload")
    async def add_document_upload(
        file: UploadFile = File(...),
        strategy: str | None = Form(default=None),
        scope: str = Form(default="session"),
        owner_id: str = Form(default=""),
    ) -> dict[str, Any]:
        raw = await file.read()
        if len(raw) > 5_000_000:
            raise HTTPException(413, detail="file too large")
        name = file.filename or "upload.txt"
        from pathlib import Path

        text = extract_text(Path(name), raw=raw)
        if not text.strip() or looks_like_pdf_garbage(text):
            raise HTTPException(
                422,
                detail=(
                    "Не удалось извлечь текст из файла. "
                    "Для PDF нужен текстовый слой (не скан); попробуйте .md / .txt."
                ),
            )
        return await pipeline().add_document(
            text=text,
            source=name,
            title=Path(name).stem,
            strategy=strategy,
            scope=scope,
            owner_id=owner_id,
        )

    @app.get("/v1/documents")
    async def list_documents(
        owner_id: str | None = None,
        include_stand: bool = False,
        all_owners: bool = False,
    ) -> dict[str, Any]:
        return pipeline().list_documents(
            owner_id=owner_id,
            include_stand=include_stand,
            all_owners=all_owners,
        )

    @app.post("/v1/search")
    async def search(body: SearchRequest) -> dict[str, Any]:
        return await pipeline().search_payload(
            body.query,
            top_k=body.top_k,
            mode=body.mode,
            top_k_pre=body.top_k_pre,
            top_k_post=body.top_k_post or body.top_k,
            min_score=body.min_score,
            owner_id=body.owner_id,
        )

    @app.post("/v1/ask")
    async def ask(body: SearchRequest) -> dict[str, Any]:
        """Return retrieved context block for the caller LLM (no LLM here)."""
        payload = await pipeline().search_payload(
            body.query,
            top_k=body.top_k,
            mode=body.mode,
            top_k_pre=body.top_k_pre,
            top_k_post=body.top_k_post or body.top_k,
            min_score=body.min_score,
            owner_id=body.owner_id,
        )
        hits = payload["hits"]
        assert isinstance(hits, list)
        lines = []
        for i, hit in enumerate(hits, start=1):
            assert isinstance(hit, dict)
            lines.append(
                f"[{i}] {hit.get('title')} · {hit.get('section')} ({hit.get('source')})\n"
                f"{hit.get('text')}"
            )
        context = "\n\n".join(lines)
        return {
            **payload,
            "context": context,
            "prompt_suffix": (
                "Ответь на вопрос, опираясь на фрагменты ниже. "
                "Если в фрагментах нет ответа — скажи об этом.\n\n"
                f"{context}"
            ),
        }

    @app.patch("/v1/settings")
    async def patch_settings(body: SettingsPatch) -> dict[str, Any]:
        s = cfg()
        if body.local_embeddings is not None:
            s.local_embeddings_enabled = body.local_embeddings
            if body.local_embeddings:
                s.embedding_provider = "local"
            else:
                s.embedding_provider = "api"
        if body.embedding_provider is not None:
            s.embedding_provider = body.embedding_provider
        if body.chunk_strategy is not None:
            s.rag_chunk_strategy = body.chunk_strategy
        # Rebuild embedder when provider flips.
        old = state["embedder"]
        close = getattr(old, "aclose", None)
        if close is not None:
            await close()
        state["embedder"] = build_embedder(s)
        state["pipeline"] = RagPipeline(s, state["store"], state["embedder"])
        get_settings.cache_clear()
        return await stats()

    app.state.rag = state  # type: ignore[attr-defined]
    return app
