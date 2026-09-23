"""MCP catalog seen by the stand (names + descriptions only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class McpToolInfo:
    name: str
    description: str


@dataclass(frozen=True)
class McpCatalog:
    connected: bool
    protocol: str
    server: str
    tools: tuple[McpToolInfo, ...]
    error: str | None = None


class McpCatalogPort(Protocol):
    async def fetch(self) -> McpCatalog: ...
