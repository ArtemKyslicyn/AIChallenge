import json

import httpx
import pytest

from app.adapters.guest_mcp_http import GuestMcpAuthError, HttpGuestMcpClient


def _handler(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content.decode())
    if body.get("method") == "initialize":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "kit"},
                },
            },
        )
    if body.get("method") == "tools/list":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"tools": [{"name": "echo", "description": "ping"}]},
            },
        )
    if body.get("method") == "tools/call":
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"content": [{"type": "text", "text": "ok"}]},
            },
        )
    return httpx.Response(404, json={"error": "no"})


async def test_handshake_lists_tools() -> None:
    transport = httpx.MockTransport(_handler)
    client = HttpGuestMcpClient(transport=transport)
    tools = await client.handshake("https://kit.example.com/mcp", "tok")
    assert tools == ("echo",)


async def test_401_is_auth_error() -> None:
    def deny(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "no"})

    client = HttpGuestMcpClient(transport=httpx.MockTransport(deny))
    with pytest.raises(GuestMcpAuthError):
        await client.handshake("https://kit.example.com/mcp", "bad")
