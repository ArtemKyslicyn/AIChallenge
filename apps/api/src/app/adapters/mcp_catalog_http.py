"""HTTP catalog from the MCP sidecar (Bearer). Not the MCP wire protocol."""

from __future__ import annotations

import httpx

from app.domain.mcp_catalog import McpCatalog, McpToolInfo


class HttpMcpCatalog:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    async def fetch(self) -> McpCatalog:
        if not self._token:
            return McpCatalog(
                connected=False,
                protocol="mcp",
                server="",
                tools=(),
                error="MCP_SHARED_TOKEN unset",
            )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{self._base}/catalog",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.HTTPError:
            return McpCatalog(
                connected=False,
                protocol="mcp",
                server="",
                tools=(),
                error="mcp unreachable",
            )
        if response.status_code != 200:
            return McpCatalog(
                connected=False,
                protocol="mcp",
                server="",
                tools=(),
                error=f"catalog HTTP {response.status_code}",
            )
        payload = response.json()
        tools = tuple(
            McpToolInfo(
                name=str(item.get("name") or ""),
                description=str(item.get("description") or ""),
            )
            for item in payload.get("tools") or []
            if item.get("name")
        )
        return McpCatalog(
            connected=bool(payload.get("connected", True)),
            protocol=str(payload.get("protocol") or "mcp"),
            server=str(payload.get("server") or ""),
            tools=tools,
        )


class FakeMcpCatalog:
    async def fetch(self) -> McpCatalog:
        return McpCatalog(
            connected=True,
            protocol="mcp",
            server="aichallenge-mcp",
            tools=(
                McpToolInfo("echo", "Return the given text unchanged."),
                McpToolInfo("time_now", "Current UTC time as ISO-8601."),
                McpToolInfo(
                    "list_stages",
                    "Task stages used on the stand: planning, execution, validation, done.",
                ),
            ),
        )
