"""Return the MCP tool list for the UI. Failures stay a disconnected catalog."""

from __future__ import annotations

from app.domain.mcp_catalog import McpCatalog, McpCatalogPort


async def list_mcp_tools(catalog: McpCatalogPort) -> McpCatalog:
    return await catalog.fetch()
