"""ASGI app: Streamable HTTP MCP plus /health, /catalog, /invoke, /pulse."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from starlette.applications import Starlette

from aichallenge_mcp.auth import BearerAuthMiddleware
from aichallenge_mcp.pulse import run_scheduler
from aichallenge_mcp.server import mcp

app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)

_original = app.router.lifespan_context


@asynccontextmanager
async def _pulse_lifespan(instance: Starlette) -> AsyncIterator[None]:
    task = asyncio.create_task(run_scheduler(), name="stand-pulse")
    try:
        if _original is not None:
            async with _original(instance):
                yield
        else:
            yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app.router.lifespan_context = _pulse_lifespan
