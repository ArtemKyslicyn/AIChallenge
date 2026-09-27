"""Connect, list, enable, and disconnect session-scoped guest MCP servers."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from uuid import UUID, uuid4

from app.application.guest_mcp_analytics import emit_guest_event
from app.domain.guest_mcp import (
    GuestMcpClient,
    GuestMcpRecord,
    GuestMcpRegistry,
    GuestMcpServer,
    GuestMcpUrlError,
    assert_guest_mcp_resolved,
    assert_guest_mcp_url,
    url_host,
)
from app.domain.analytics import AnalyticsCapture

HANDSHAKE_TIMEOUT_S = 8


class GuestMcpAuthError(Exception):
    """Bearer rejected by the guest MCP server."""


class GuestMcpUnreachableError(Exception):
    """Guest MCP server could not be reached."""


def _url_fail_reason(err: GuestMcpUrlError) -> str:
    msg = err.message
    if "blocked" in msg or "loopback" in msg or "нельзя вызвать" in msg:
        return "ssrf"
    return "bad_url"


async def connect_guest_mcp(
    session_id: UUID,
    name: str,
    url: str,
    token: str,
    *,
    client: GuestMcpClient,
    registry: GuestMcpRegistry,
    analytics: AnalyticsCapture,
    distinct_id: str,
    allow_loopback: bool,
) -> GuestMcpServer:
    host = url_host(url)
    has_token = bool(token.strip())
    await emit_guest_event(
        analytics,
        "guest_mcp_connect_started",
        distinct_id,
        {"url_host": host, "has_token": has_token},
    )

    try:
        normalized = assert_guest_mcp_url(url, allow_loopback=allow_loopback)
        assert_guest_mcp_resolved(url_host(normalized), allow_loopback=allow_loopback)
    except GuestMcpUrlError as exc:
        await emit_guest_event(
            analytics,
            "guest_mcp_connect_fail",
            distinct_id,
            {"url_host": host, "reason": _url_fail_reason(exc)},
        )
        raise

    started = time.monotonic()
    try:
        tool_names = await asyncio.wait_for(
            client.handshake(normalized, token),
            timeout=HANDSHAKE_TIMEOUT_S,
        )
    except TimeoutError as exc:
        await emit_guest_event(
            analytics,
            "guest_mcp_connect_fail",
            distinct_id,
            {"url_host": host, "reason": "timeout"},
        )
        raise
    except asyncio.TimeoutError:
        await emit_guest_event(
            analytics,
            "guest_mcp_connect_fail",
            distinct_id,
            {"url_host": host, "reason": "timeout"},
        )
        raise TimeoutError("guest MCP handshake timed out")
    except GuestMcpAuthError:
        await emit_guest_event(
            analytics,
            "guest_mcp_connect_fail",
            distinct_id,
            {"url_host": host, "reason": "unauthorized"},
        )
        raise
    except GuestMcpUnreachableError:
        await emit_guest_event(
            analytics,
            "guest_mcp_connect_fail",
            distinct_id,
            {"url_host": host, "reason": "unreachable"},
        )
        raise
    except GuestMcpUrlError as exc:
        await emit_guest_event(
            analytics,
            "guest_mcp_connect_fail",
            distinct_id,
            {"url_host": host, "reason": _url_fail_reason(exc)},
        )
        raise

    latency_ms = int((time.monotonic() - started) * 1000)
    server = GuestMcpServer(
        id=uuid4(),
        name=name.strip() or host,
        url=normalized,
        enabled=True,
        tool_names=tuple(tool_names),
        status="connected",
    )
    await registry.put(session_id, GuestMcpRecord(server=server, token=token))
    await emit_guest_event(
        analytics,
        "guest_mcp_connect_ok",
        distinct_id,
        {
            "url_host": url_host(normalized),
            "tool_count": len(tool_names),
            "latency_ms": latency_ms,
        },
    )
    return server


async def list_guest_mcp(
    session_id: UUID,
    registry: GuestMcpRegistry,
) -> tuple[GuestMcpServer, ...]:
    records = await registry.list(session_id)
    return tuple(r.server for r in records)


async def set_guest_enabled(
    session_id: UUID,
    server_id: UUID,
    enabled: bool,
    *,
    registry: GuestMcpRegistry,
    analytics: AnalyticsCapture,
    distinct_id: str,
) -> GuestMcpServer:
    record = await registry.get(session_id, server_id)
    if record is None:
        raise KeyError(server_id)
    server = replace(record.server, enabled=enabled)
    await registry.put(session_id, GuestMcpRecord(server=server, token=record.token))
    await emit_guest_event(
        analytics,
        "guest_mcp_toggled",
        distinct_id,
        {"enabled": enabled, "url_host": url_host(server.url)},
    )
    return server


async def disconnect_guest_mcp(
    session_id: UUID,
    server_id: UUID,
    *,
    registry: GuestMcpRegistry,
    analytics: AnalyticsCapture,
    distinct_id: str,
) -> None:
    record = await registry.get(session_id, server_id)
    if record is None:
        raise KeyError(server_id)
    host = url_host(record.server.url)
    await registry.delete(session_id, server_id)
    await emit_guest_event(
        analytics,
        "guest_mcp_disconnect",
        distinct_id,
        {"url_host": host},
    )
