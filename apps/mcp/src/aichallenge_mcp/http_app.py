"""ASGI app: Streamable HTTP MCP plus /health and /catalog."""

from __future__ import annotations

from aichallenge_mcp.auth import BearerAuthMiddleware
from aichallenge_mcp.server import mcp

app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)
