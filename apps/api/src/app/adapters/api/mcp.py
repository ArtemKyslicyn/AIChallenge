"""Public catalog of MCP tools. Token stays on the server."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.adapters.mcp_catalog_http import HttpMcpCatalog
from app.application.list_mcp_tools import list_mcp_tools
from app.core.deps import get_container

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/tools")
async def mcp_tools(request: Request) -> dict[str, object]:
    settings = get_container(request).settings
    catalog = await list_mcp_tools(HttpMcpCatalog(settings.mcp_base_url, settings.mcp_shared_token))
    return {
        "connected": catalog.connected,
        "protocol": catalog.protocol,
        "server": catalog.server,
        "tools": [{"name": tool.name, "description": tool.description} for tool in catalog.tools],
        "error": catalog.error,
    }
