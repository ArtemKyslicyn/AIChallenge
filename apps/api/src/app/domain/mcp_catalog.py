"""MCP catalog and tool-runner ports seen by the stand."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class McpToolInfo:
    name: str
    description: str
    parameters: dict[str, Any] | None = None


@dataclass(frozen=True)
class McpCatalog:
    connected: bool
    protocol: str
    server: str
    tools: tuple[McpToolInfo, ...]
    error: str | None = None


@dataclass(frozen=True)
class McpToolCall:
    name: str
    arguments: dict[str, Any]
    result: str


@dataclass(frozen=True)
class McpPulseSnapshot:
    jobs: tuple[dict[str, Any], ...]
    latest_digest: dict[str, Any] | None
    latest_id: str | None = None
    latest_at: str | None = None
    error: str | None = None
    watch: dict[str, Any] | None = None
    incidents: tuple[dict[str, Any], ...] = ()
    next_action: dict[str, Any] | None = None
    latest_brief: dict[str, Any] | None = None


class McpCatalogPort(Protocol):
    async def fetch(self) -> McpCatalog: ...


class McpToolRunner(Protocol):
    async def openai_tools(self) -> list[dict[str, object]]: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str: ...
