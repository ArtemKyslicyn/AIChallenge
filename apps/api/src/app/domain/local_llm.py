"""Per-user Ollama origin. The browser never calls Ollama itself."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID

LOCAL_LLM_PREFIX = "ollama/"
BLOCKED_ORIGIN = "Этот адрес подключить нельзя."
FORBIDDEN_MESSAGE = "Локальная модель доступна только администратору."

_BLOCKED_HOSTS = frozenset(
    {
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.internal",
    }
)
_LOOPBACK_NAMES = frozenset({"localhost", "host.docker.internal"})
_CGNAT = ipaddress.ip_network("100.64.0.0/10")

ResolveFn = Callable[[str], tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]]


class LocalLlmUrlError(ValueError):
    def __init__(self, message: str = BLOCKED_ORIGIN) -> None:
        super().__init__(message)
        self.message = message


class LocalLlmForbiddenError(ValueError):
    """Signed-in user is not on the local-LLM email allowlist."""

    def __init__(self, message: str = FORBIDDEN_MESSAGE) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True)
class LocalLlmSource:
    user_id: UUID
    name: str
    base_url: str
    api_key: str | None
    enabled: bool
    models: tuple[str, ...]
    status: str
    safe_error: str | None


class LocalLlmRepository(Protocol):
    async def get_for_user(self, user_id: UUID) -> LocalLlmSource | None: ...

    async def upsert(self, source: LocalLlmSource) -> None: ...

    async def delete_for_user(self, user_id: UUID) -> None: ...


def canonical_model_id(upstream: str) -> str:
    tag = upstream.strip()
    if not tag or any(ch.isspace() for ch in tag) or "/" in tag:
        raise LocalLlmUrlError("Некорректный id модели.")
    return f"{LOCAL_LLM_PREFIX}{tag}"


def upstream_model_id(model_id: str) -> str | None:
    if not model_id.startswith(LOCAL_LLM_PREFIX):
        return None
    tag = model_id[len(LOCAL_LLM_PREFIX) :]
    if not tag or any(ch.isspace() for ch in tag) or "/" in tag:
        return None
    return tag


def assert_local_llm_email_allowed(email: str, allowed_emails_csv: str) -> None:
    """If allowlist is non-empty, email must be on it (case-insensitive)."""
    allowed = {
        part.strip().lower() for part in (allowed_emails_csv or "").split(",") if part.strip()
    }
    if not allowed:
        return
    normalized = (email or "").strip().lower()
    if normalized not in allowed:
        raise LocalLlmForbiddenError()


def _origin_allowlist_entries(csv: str) -> set[str]:
    return {part.strip().lower() for part in (csv or "").split(",") if part.strip()}


def assert_local_llm_origin_allowed(canonical_origin: str, allowlist_csv: str) -> None:
    """If allowlist is non-empty, hostname or host:port must match an entry."""
    allowed = _origin_allowlist_entries(allowlist_csv)
    if not allowed:
        return
    parsed = urlparse(canonical_origin)
    host = (parsed.hostname or "").lower()
    if not host:
        raise LocalLlmUrlError(BLOCKED_ORIGIN)
    host_port = host if parsed.port is None else f"{host}:{parsed.port}"
    if host in allowed or host_port in allowed:
        return
    raise LocalLlmUrlError(BLOCKED_ORIGIN)


def _check_ip(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    *,
    allow_loopback: bool,
    allow_tailscale: bool,
    allow_private: bool,
) -> None:
    if ip.is_link_local or str(ip) == "169.254.169.254":
        raise LocalLlmUrlError(BLOCKED_ORIGIN)
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT:
        if not allow_tailscale:
            raise LocalLlmUrlError(BLOCKED_ORIGIN)
        return
    if ip.is_loopback:
        if not allow_loopback:
            raise LocalLlmUrlError(BLOCKED_ORIGIN)
        return
    if ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        if not allow_private:
            raise LocalLlmUrlError(BLOCKED_ORIGIN)


def _default_resolve(host: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, ...]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise LocalLlmUrlError(BLOCKED_ORIGIN) from exc
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
        raise LocalLlmUrlError(BLOCKED_ORIGIN)
    return tuple(ips)


def assert_local_llm_resolved(
    host: str,
    *,
    allow_loopback: bool,
    allow_tailscale: bool,
    allow_private: bool,
    resolve: ResolveFn | None = None,
) -> None:
    normalized_host = host.lower()
    resolver = resolve or _default_resolve
    for ip in resolver(normalized_host):
        _check_ip(
            ip,
            allow_loopback=allow_loopback,
            allow_tailscale=allow_tailscale,
            allow_private=allow_private,
        )


def canonicalize_ollama_origin(
    url: str,
    *,
    allow_loopback: bool,
    allow_tailscale: bool,
    allow_private: bool,
) -> str:
    """Keep scheme, host, and port. Drop path, query, and userinfo."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise LocalLlmUrlError(BLOCKED_ORIGIN)
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTS or host.startswith("169.254."):
        raise LocalLlmUrlError(BLOCKED_ORIGIN)
    try:
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        _check_ip(
            ip,
            allow_loopback=allow_loopback,
            allow_tailscale=allow_tailscale,
            allow_private=allow_private,
        )
    elif host in _LOOPBACK_NAMES:
        if not allow_loopback:
            raise LocalLlmUrlError(BLOCKED_ORIGIN)
    elif parsed.scheme != "https":
        raise LocalLlmUrlError(BLOCKED_ORIGIN)
    netloc_host = f"[{host}]" if ":" in host else host
    netloc = netloc_host if parsed.port is None else f"{netloc_host}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}"


def validate_ollama_origin(
    url: str,
    *,
    allow_loopback: bool,
    allow_tailscale: bool,
    allow_private: bool,
    origin_allowlist_csv: str = "",
    resolve: ResolveFn | None = None,
) -> str:
    """Canonicalize, enforce origin allowlist, and resolve hostnames against IP policy."""
    origin = canonicalize_ollama_origin(
        url,
        allow_loopback=allow_loopback,
        allow_tailscale=allow_tailscale,
        allow_private=allow_private,
    )
    assert_local_llm_origin_allowed(origin, origin_allowlist_csv)
    host = (urlparse(origin).hostname or "").lower()
    try:
        ipaddress.ip_address(host)
        literal_ip = True
    except ValueError:
        literal_ip = False
    if not literal_ip and host not in _LOOPBACK_NAMES:
        assert_local_llm_resolved(
            host,
            allow_loopback=allow_loopback,
            allow_tailscale=allow_tailscale,
            allow_private=allow_private,
            resolve=resolve,
        )
    return origin


_current: ContextVar[LocalLlmSource | None] = ContextVar("local_llm_source", default=None)


def set_local_llm_source(source: LocalLlmSource | None) -> Token[LocalLlmSource | None]:
    return _current.set(source)


def reset_local_llm_source(token: Token[LocalLlmSource | None]) -> None:
    _current.reset(token)


def current_local_llm_source() -> LocalLlmSource | None:
    return _current.get()
