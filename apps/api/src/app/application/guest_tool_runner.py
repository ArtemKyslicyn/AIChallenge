"""OpenAI-shaped tools for session-scoped guest MCP servers."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain.analytics import AnalyticsCapture
from app.domain.guest_mcp import GuestMcpClient, GuestMcpRecord, GuestMcpRegistry, url_host

_MAX_OPENAI_NAME = 64


def guest_tool_openai_name(server_id: UUID, tool_name: str) -> str:
    return f"g_{server_id.hex[:8]}_{tool_name}"[:_MAX_OPENAI_NAME]


def parse_guest_tool_openai_name(
    prefixed: str, records: tuple[GuestMcpRecord, ...]
) -> tuple[GuestMcpRecord, str] | None:
    if not prefixed.startswith("g_"):
        return None
    rest = prefixed[2:]
    sep = rest.find("_")
    if sep < 1:
        return None
    sid_prefix = rest[:sep]
    raw_tool = rest[sep + 1 :]
    if not raw_tool:
        return None
    for record in records:
        if record.server.id.hex[:8] != sid_prefix:
            continue
        if raw_tool in record.server.tool_names:
            return record, raw_tool
    return None


class GuestToolRunner:
    """Builds prefixed OpenAI tools and calls guest MCP by session record."""

    def __init__(
        self,
        *,
        session_id: UUID,
        registry: GuestMcpRegistry,
        client: GuestMcpClient,
        analytics: AnalyticsCapture | None = None,
        distinct_id: str = "",
    ) -> None:
        self._session_id = session_id
        self._registry = registry
        self._client = client
        self._analytics = analytics
        self._distinct_id = distinct_id
        self._records: tuple[GuestMcpRecord, ...] = ()

    async def _enabled_records(self) -> tuple[GuestMcpRecord, ...]:
        listed = await self._registry.list(self._session_id)
        return tuple(
            r
            for r in listed
            if r.server.enabled and r.server.status == "connected" and r.server.tool_names
        )

    async def openai_tools(self) -> list[dict[str, object]]:
        self._records = await self._enabled_records()
        tools: list[dict[str, object]] = []
        for record in self._records:
            for tool_name in record.server.tool_names:
                openai_name = guest_tool_openai_name(record.server.id, tool_name)
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": openai_name,
                            "description": f"[{record.server.name}] {tool_name}",
                            "parameters": {"type": "object", "properties": {}},
                        },
                    }
                )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if not self._records:
            self._records = await self._enabled_records()
        matched = parse_guest_tool_openai_name(name, self._records)
        if matched is None:
            raise ValueError(f"unknown guest tool: {name}")
        record, raw_tool = matched
        return await self._client.call_tool(
            record.server.url,
            record.token,
            raw_tool,
            dict(arguments or {}),
        )

    def display_name(self, prefixed: str) -> tuple[str, str]:
        """Raw tool name and guest server label for SSE."""
        if not self._records:
            return prefixed, ""
        matched = parse_guest_tool_openai_name(prefixed, self._records)
        if matched is None:
            return prefixed, ""
        record, raw_tool = matched
        return raw_tool, record.server.name

    def url_host_for(self, prefixed: str) -> str:
        if not self._records:
            return ""
        matched = parse_guest_tool_openai_name(prefixed, self._records)
        if matched is None:
            return ""
        return url_host(matched[0].server.url)
