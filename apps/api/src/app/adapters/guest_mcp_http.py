"""Streamable HTTP JSON-RPC client for session-scoped guest MCP servers."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.application.guest_mcp import GuestMcpAuthError, GuestMcpUnreachableError

HANDSHAKE_TIMEOUT_S = 8.0
CALL_TIMEOUT_S = 12.0

_ACCEPT = "application/json, text/event-stream"
_CLIENT_INFO = {"name": "aichallenge-guest", "version": "1"}
_PROTOCOL_VERSION = "2024-11-05"

__all__ = ["GuestMcpAuthError", "GuestMcpUnreachableError", "HttpGuestMcpClient"]


def _headers(token: str) -> dict[str, str]:
    headers = {
        "Accept": _ACCEPT,
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_body(response: httpx.Response) -> dict[str, Any]:
    content_type = (response.headers.get("content-type") or "").lower()
    raw = response.text
    if "text/event-stream" in content_type or raw.lstrip().startswith("data:"):
        for line in raw.splitlines():
            stripped = line.strip()
            if stripped.startswith("data:"):
                payload = stripped[len("data:") :].strip()
                if payload and payload != "[DONE]":
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict):
                        return parsed
        raise GuestMcpUnreachableError("guest MCP returned empty SSE stream")
    data = response.json()
    if not isinstance(data, dict):
        raise GuestMcpUnreachableError("guest MCP returned invalid JSON")
    return data


def _rpc_error(payload: dict[str, Any]) -> str:
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or "rpc error")
    return "rpc error"


def _tool_names_from_result(result: object) -> tuple[str, ...]:
    if not isinstance(result, dict):
        return ()
    tools_raw = result.get("tools")
    if not isinstance(tools_raw, list):
        return ()
    names: list[str] = []
    for item in tools_raw:
        if isinstance(item, dict):
            name = str(item.get("name") or "")
            if name:
                names.append(name)
    return tuple(names)


def _format_tool_result(result: object) -> str:
    if not isinstance(result, dict):
        return json.dumps(result, ensure_ascii=False)
    content = result.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        if parts:
            return "".join(parts)
    return json.dumps(result, ensure_ascii=False)


class HttpGuestMcpClient:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._rpc_id = 0

    def _next_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    async def _post_rpc(
        self,
        url: str,
        token: str,
        method: str,
        params: dict[str, object] | None,
        *,
        timeout_s: float,
    ) -> dict[str, Any]:
        body = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        try:
            async with httpx.AsyncClient(
                transport=self._transport,
                timeout=timeout_s,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    url,
                    headers=_headers(token),
                    json=body,
                )
        except httpx.HTTPError:
            raise GuestMcpUnreachableError("guest MCP unreachable") from None
        if response.status_code == 401:
            raise GuestMcpAuthError("guest MCP unauthorized")
        if response.status_code >= 400:
            raise GuestMcpUnreachableError(f"guest MCP HTTP {response.status_code}")
        payload = _parse_body(response)
        if payload.get("error"):
            raise GuestMcpUnreachableError(_rpc_error(payload))
        return payload

    async def handshake(self, url: str, token: str) -> tuple[str, ...]:
        init = await self._post_rpc(
            url,
            token,
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            },
            timeout_s=HANDSHAKE_TIMEOUT_S,
        )
        if "result" not in init:
            raise GuestMcpUnreachableError("guest MCP initialize failed")
        listed = await self._post_rpc(
            url,
            token,
            "tools/list",
            {},
            timeout_s=HANDSHAKE_TIMEOUT_S,
        )
        result = listed.get("result")
        return _tool_names_from_result(result)

    async def call_tool(
        self, url: str, token: str, name: str, arguments: dict[str, object]
    ) -> str:
        payload = await self._post_rpc(
            url,
            token,
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout_s=CALL_TIMEOUT_S,
        )
        return _format_tool_result(payload.get("result"))
