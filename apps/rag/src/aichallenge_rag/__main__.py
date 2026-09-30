"""Run RAG HTTP (+ MCP) service."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from aichallenge_rag.auth import BearerAuthMiddleware
from aichallenge_rag.http_app import create_app
from aichallenge_rag.mcp_server import bind_runtime, mcp
from aichallenge_rag.settings import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    if settings.rag_shared_token and not os.environ.get("RAG_SHARED_TOKEN"):
        os.environ["RAG_SHARED_TOKEN"] = settings.rag_shared_token

    app = create_app(settings)
    app.add_middleware(BearerAuthMiddleware)

    original = app.router.lifespan_context

    @asynccontextmanager
    async def with_mcp_bind(instance: FastAPI):
        async with original(instance):
            state = instance.state.rag  # type: ignore[attr-defined]
            bind_runtime(
                pipeline=state["pipeline"],
                store=state["store"],
                settings=state["settings"],
            )
            yield

    app.router.lifespan_context = with_mcp_bind

    try:
        app.mount("/mcp", mcp.streamable_http_app())
    except Exception:
        logger.exception("MCP mount failed")

    uvicorn.run(app, host=settings.rag_host, port=settings.rag_port, log_level="info")


if __name__ == "__main__":
    main()
