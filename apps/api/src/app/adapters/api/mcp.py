"""Public catalog, pulse, and operator invoke. Token stays on the server."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.adapters.mcp_catalog_http import HttpMcpCatalog, HttpMcpPulse, HttpMcpToolRunner
from app.application.list_mcp_tools import list_mcp_tools
from app.core.deps import get_container

router = APIRouter(prefix="/mcp", tags=["mcp"])

ALLOWED_INVOKE = frozenset(
    {
        "probe_stand",
        "model_pulse",
        "schedule_digest",
        "latest_digest",
        "list_jobs",
        "watch_brief",
        "ack_incident",
        "probe_history",
        "search",
        "summarize",
        "saveToFile",
    }
)


class McpInvokeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    arguments: dict[str, Any] = Field(default_factory=dict)


@router.get("/tools")
async def mcp_tools(request: Request) -> dict[str, object]:
    settings = get_container(request).settings
    catalog = await list_mcp_tools(HttpMcpCatalog(settings.mcp_base_url, settings.mcp_shared_token))
    return {
        "connected": catalog.connected,
        "protocol": catalog.protocol,
        "server": catalog.server,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "server": tool.server,
            }
            for tool in catalog.tools
        ],
        "error": catalog.error,
    }


@router.get("/pulse")
async def mcp_pulse(request: Request) -> dict[str, object]:
    settings = get_container(request).settings
    snapshot = await HttpMcpPulse(settings.mcp_base_url, settings.mcp_shared_token).fetch()
    return {
        "jobs": list(snapshot.jobs),
        "latest_digest": snapshot.latest_digest,
        "latest_id": snapshot.latest_id,
        "latest_at": snapshot.latest_at,
        "error": snapshot.error,
        "watch": snapshot.watch,
        "incidents": list(snapshot.incidents),
        "next_action": snapshot.next_action,
        "latest_brief": snapshot.latest_brief,
    }


@router.post("/invoke")
async def mcp_invoke(payload: McpInvokeRequest, request: Request) -> dict[str, object]:
    name = payload.name.strip()
    if name not in ALLOWED_INVOKE:
        raise HTTPException(status_code=400, detail="unknown operator tool")
    settings = get_container(request).settings
    runner = HttpMcpToolRunner(settings.mcp_base_url, settings.mcp_shared_token)
    result = await runner.call_tool(name, payload.arguments)
    return {"name": name, "result": result}
