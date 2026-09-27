"""Session-scoped guest MCP. Stand Pulse is a different port."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

GUEST_MCP_BLOCKED_HOSTS = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.internal",
    }
)


class GuestMcpUrlError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


GuestMcpStatus = str  # "connected" | "error" | "off"


@dataclass(frozen=True)
class GuestMcpServer:
    id: UUID
    name: str
    url: str
    enabled: bool
    tool_names: tuple[str, ...]
    status: GuestMcpStatus
    safe_error: str | None = None


@dataclass
class GuestMcpRecord:
    server: GuestMcpServer
    token: str


def url_host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def assert_guest_mcp_url(url: str, *, allow_loopback: bool) -> str:
    raw = url.strip()
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise GuestMcpUrlError("Нужен полный адрес, с http://.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise GuestMcpUrlError("Укажите адрес сервера")
    if host in GUEST_MCP_BLOCKED_HOSTS or host.startswith("169.254."):
        raise GuestMcpUrlError("Этот адрес нельзя вызвать с сервера (blocked).")
    loopback = host in {"127.0.0.1", "localhost", "::1"}
    if parsed.scheme == "http" and not loopback:
        raise GuestMcpUrlError("Нужен полный адрес, с https://.")
    if loopback and not allow_loopback:
        raise GuestMcpUrlError("Этот адрес нельзя вызвать с сервера (loopback).")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (ip.is_private or ip.is_link_local or ip.is_loopback) and not (
        loopback and allow_loopback
    ):
        raise GuestMcpUrlError("Этот адрес нельзя вызвать с сервера.")
    return raw.rstrip("/")


class GuestMcpClient(Protocol):
    async def handshake(self, url: str, token: str) -> tuple[str, ...]: ...

    async def call_tool(
        self, url: str, token: str, name: str, arguments: dict[str, object]
    ) -> str: ...


class GuestMcpRegistry(Protocol):
    async def list(self, session_id: UUID) -> tuple[GuestMcpRecord, ...]: ...

    async def put(self, session_id: UUID, record: GuestMcpRecord) -> None: ...

    async def get(self, session_id: UUID, server_id: UUID) -> GuestMcpRecord | None: ...

    async def delete(self, session_id: UUID, server_id: UUID) -> None: ...
