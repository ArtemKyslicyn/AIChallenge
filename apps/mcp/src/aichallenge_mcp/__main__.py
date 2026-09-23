"""stdio (default) or HTTP (`MCP_TRANSPORT=http`)."""

from __future__ import annotations

import os


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if transport in {"http", "streamable-http", "sse"}:
        import uvicorn

        from aichallenge_mcp.http_app import app

        host = os.environ.get("MCP_HOST", "0.0.0.0")
        port = int(os.environ.get("MCP_PORT", "18765"))
        uvicorn.run(app, host=host, port=port)
        return
    from aichallenge_mcp.server import mcp

    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
