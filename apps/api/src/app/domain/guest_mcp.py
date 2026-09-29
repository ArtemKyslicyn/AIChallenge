"""Session-scoped guest MCP. Stand Pulse is a different port."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
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

ResolveFn = Callable[[str], tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]]


class GuestMcpUrlError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class GuestMcpForbiddenError(ValueError):
    """Signed-in user is not on the Guest MCP allowlist."""

    def __init__(self, message: str = "Guest MCP доступен только администратору.") -> None:
        super().__init__(message)
        self.message = message


def assert_guest_mcp_email_allowed(email: str, allowed_emails_csv: str) -> None:
    """If allowlist is non-empty, email must be on it (case-insensitive)."""
    allowed = {
        part.strip().lower() for part in (allowed_emails_csv or "").split(",") if part.strip()
    }
    if not allowed:
        return
    normalized = (email or "").strip().lower()
    if normalized not in allowed:
        raise GuestMcpForbiddenError()


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


def _loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def _canonical_guest_mcp_url(parsed: object) -> str:
    from urllib.parse import ParseResult

    if not isinstance(parsed, ParseResult):
        raise TypeError("expected ParseResult")
    hostname = parsed.hostname
    if not hostname:
        raise GuestMcpUrlError("Укажите адрес сервера")
    netloc = hostname if parsed.port is None else f"{hostname}:{parsed.port}"
    path = parsed.path or ""
    canonical = f"{parsed.scheme}://{netloc}{path}"
    return canonical.rstrip("/")


def _reject_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    host: str,
    allow_loopback: bool,
) -> None:
    loopback_host = _loopback_host(host)
    if str(ip) == "169.254.169.254" or ip.is_link_local:
        raise GuestMcpUrlError("Этот адрес нельзя вызвать с сервера (blocked).")
    if ip.is_loopback:
        if not (loopback_host and allow_loopback):
            raise GuestMcpUrlError("Этот адрес нельзя вызвать с сервера (blocked).")
        return
    if ip.is_private:
        raise GuestMcpUrlError("Этот адрес нельзя вызвать с сервера (blocked).")


def _default_resolve(host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise GuestMcpUrlError("Не удалось определить адрес сервера.") from exc
    ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    seen: set[str] = set()
    for family, _, _, _, sockaddr in infos:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        addr = sockaddr[0]
        if not isinstance(addr, str):
            continue
        if addr in seen:
            continue
        seen.add(addr)
        ips.append(ipaddress.ip_address(addr))
    if not ips:
        raise GuestMcpUrlError("Не удалось определить адрес сервера.")
    return tuple(ips)


def assert_guest_mcp_resolved(
    host: str,
    *,
    allow_loopback: bool,
    resolve: ResolveFn | None = None,
) -> None:
    normalized_host = host.lower()
    resolver = resolve or _default_resolve
    for ip in resolver(normalized_host):
        _reject_ip(ip, host=normalized_host, allow_loopback=allow_loopback)


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
    loopback = _loopback_host(host)
    if parsed.scheme == "http" and not loopback:
        raise GuestMcpUrlError("Нужен полный адрес, с https://.")
    if loopback and not allow_loopback:
        raise GuestMcpUrlError("Этот адрес нельзя вызвать с сервера (loopback).")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        _reject_ip(ip, host=host, allow_loopback=allow_loopback)
    return _canonical_guest_mcp_url(parsed)


class GuestMcpClient(Protocol):
    async def handshake(self, url: str, token: str) -> tuple[str, ...]: ...

    async def call_tool(
        self, url: str, token: str, name: str, arguments: dict[str, object]
    ) -> str: ...


class GuestMcpRegistry(Protocol):
    async def list(self, owner_id: UUID) -> tuple[GuestMcpRecord, ...]: ...

    async def put(self, owner_id: UUID, record: GuestMcpRecord) -> None: ...

    async def get(self, owner_id: UUID, server_id: UUID) -> GuestMcpRecord | None: ...

    async def delete(self, owner_id: UUID, server_id: UUID) -> None: ...
