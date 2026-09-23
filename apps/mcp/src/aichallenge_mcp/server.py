"""Local MCP server with a small neutral tool catalog."""

from __future__ import annotations

from datetime import UTC, datetime

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

SERVER_NAME = "aichallenge-mcp"
TASK_STAGES = ("planning", "execution", "validation", "done")
EXPECTED_TOOL_NAMES = frozenset({"echo", "time_now", "list_stages"})

mcp = FastMCP(
    SERVER_NAME,
    stateless_http=True,
    json_response=True,
    # Behind our nginx + Bearer token; Host is the public site name.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
def echo(text: str) -> str:
    """Return the given text unchanged."""
    return text


@mcp.tool()
def time_now() -> str:
    """Current UTC time as ISO-8601."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@mcp.tool()
def list_stages() -> str:
    """Task stages used on the stand: planning, execution, validation, done."""
    return ", ".join(TASK_STAGES)


def _tool_catalog() -> list[dict[str, str]]:
    tools = getattr(mcp, "_tool_manager").list_tools()
    return [
        {"name": tool.name, "description": (tool.description or "").strip()}
        for tool in tools
    ]


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": SERVER_NAME})


@mcp.custom_route("/catalog", methods=["GET"])
async def catalog(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "connected": True,
            "protocol": "mcp",
            "server": SERVER_NAME,
            "tools": _tool_catalog(),
        }
    )
