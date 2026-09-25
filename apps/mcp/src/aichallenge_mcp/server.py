"""Local MCP server: Day-16 catalog plus Stand Pulse tools."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from aichallenge_mcp.pulse import (
    ack_incident as ack_incident_record,
    archive_brief,
    build_digest,
    build_model_pulse,
    build_probe,
    collect_stand,
    compose_brief,
    latest_digest_payload,
    list_jobs_payload,
    probe_history as load_probe_history,
    pulse_state,
    schedule_digest_job,
    watch_brief as build_watch_brief,
)

SERVER_NAME = "aichallenge-mcp"
#: Logical MCP servers the agent routes between. Tools stay on this process.
ORCH_SERVERS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("watch", "Вахта", ("probe_stand", "watch_brief", "ack_incident", "probe_history")),
    ("models", "Модели", ("model_pulse", "schedule_digest", "latest_digest", "list_jobs")),
    ("brief", "Бриф", ("search", "summarize", "saveToFile")),
    ("stand", "Стенд", ("echo", "time_now", "list_stages")),
)


def server_for_tool(name: str) -> str:
    for server_id, _title, tools in ORCH_SERVERS:
        if name in tools:
            return server_id
    return "stand"


def orch_catalog() -> list[dict[str, Any]]:
    rows = []
    owned = {tool["name"]: tool for tool in _tool_catalog_rows()}
    for server_id, title, tools in ORCH_SERVERS:
        rows.append(
            {
                "id": server_id,
                "title": title,
                "tools": [owned[name] for name in tools if name in owned],
            }
        )
    return rows


TASK_STAGES = ("planning", "execution", "validation", "done")
EXPECTED_TOOL_NAMES = frozenset({"echo", "time_now", "list_stages"})
PULSE_TOOL_NAMES = frozenset(
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


@mcp.tool()
def probe_stand() -> str:
    """Live health of the stand API: /health status and latency in milliseconds."""
    return json.dumps(build_probe(), ensure_ascii=False)


@mcp.tool()
def model_pulse(hours: int = 24) -> str:
    """Ranked model quality and down-votes over the last N hours (Pareto + feedback)."""
    return json.dumps(build_model_pulse(hours), ensure_ascii=False)


@mcp.tool()
def schedule_digest(interval_seconds: int = 3600, hours: int = 24, note: str = "") -> str:
    """Schedule a recurring stand digest. Persists in SQLite and writes the first snapshot now."""
    return json.dumps(
        schedule_digest_job(interval_seconds, hours, note),
        ensure_ascii=False,
    )


@mcp.tool()
def latest_digest() -> str:
    """Most recent aggregated digest: health, ranking, and models that need attention."""
    return json.dumps(latest_digest_payload(), ensure_ascii=False)


@mcp.tool()
def list_jobs() -> str:
    """Scheduled Pulse jobs: interval, next run, last error."""
    return json.dumps(list_jobs_payload(), ensure_ascii=False)


@mcp.tool()
def watch_brief() -> str:
    """On-call brief: severity, open incidents, latency trend. Use this first."""
    return json.dumps(build_watch_brief(), ensure_ascii=False)


@mcp.tool()
def ack_incident(incident_id: str, note: str = "") -> str:
    """Acknowledge an open watch incident so the next brief knows an operator saw it."""
    return json.dumps(ack_incident_record(incident_id, note), ensure_ascii=False)


@mcp.tool()
def probe_history(limit: int = 12) -> str:
    """Recent /health probes from SQLite: ok flag and latency, newest first."""
    return json.dumps(load_probe_history(limit), ensure_ascii=False)


@mcp.tool()
def search(hours: int = 24) -> str:
    """Collect stand facts: /health, model ranking, open incidents. First step of the night-brief pipeline."""
    return json.dumps(collect_stand(hours), ensure_ascii=False)


@mcp.tool()
def summarize(payload: str) -> str:
    """Turn search JSON into an operator brief. Second pipeline step; pass the previous tool result."""
    return json.dumps(compose_brief(payload), ensure_ascii=False)


@mcp.tool()
def saveToFile(brief: str, name: str = "night-brief") -> str:
    """Save the summarized brief to disk and SQLite. Third pipeline step; pass summarize output."""
    return json.dumps(archive_brief(brief, name), ensure_ascii=False)


def dispatch_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
    args = dict(arguments or {})
    if name == "echo":
        return str(args.get("text") or "")
    if name == "time_now":
        return datetime.now(UTC).replace(microsecond=0).isoformat()
    if name == "list_stages":
        return ", ".join(TASK_STAGES)
    if name == "probe_stand":
        return json.dumps(build_probe(), ensure_ascii=False)
    if name == "model_pulse":
        return json.dumps(build_model_pulse(int(args.get("hours") or 24)), ensure_ascii=False)
    if name == "schedule_digest":
        return json.dumps(
            schedule_digest_job(
                int(args.get("interval_seconds") or 3600),
                int(args.get("hours") or 24),
                str(args.get("note") or ""),
            ),
            ensure_ascii=False,
        )
    if name == "latest_digest":
        return json.dumps(latest_digest_payload(), ensure_ascii=False)
    if name == "list_jobs":
        return json.dumps(list_jobs_payload(), ensure_ascii=False)
    if name == "watch_brief":
        return json.dumps(build_watch_brief(), ensure_ascii=False)
    if name == "ack_incident":
        return json.dumps(
            ack_incident_record(str(args.get("incident_id") or ""), str(args.get("note") or "")),
            ensure_ascii=False,
        )
    if name == "probe_history":
        return json.dumps(load_probe_history(int(args.get("limit") or 12)), ensure_ascii=False)
    if name == "run_digest_now":
        return json.dumps(build_digest(int(args.get("hours") or 24)), ensure_ascii=False)
    if name == "search":
        return json.dumps(collect_stand(int(args.get("hours") or 24)), ensure_ascii=False)
    if name == "summarize":
        return json.dumps(compose_brief(str(args.get("payload") or "")), ensure_ascii=False)
    if name == "saveToFile":
        return json.dumps(
            archive_brief(str(args.get("brief") or ""), str(args.get("name") or "night-brief")),
            ensure_ascii=False,
        )
    raise ValueError(f"unknown tool: {name}")


def _tool_catalog_rows() -> list[dict[str, Any]]:
    tools = getattr(mcp, "_tool_manager").list_tools()
    rows: list[dict[str, Any]] = []
    for tool in tools:
        params = getattr(tool, "parameters", None) or {
            "type": "object",
            "properties": {},
        }
        rows.append(
            {
                "name": tool.name,
                "description": (tool.description or "").strip(),
                "parameters": params,
                "server": server_for_tool(tool.name),
            }
        )
    return rows


def _tool_catalog() -> list[dict[str, Any]]:
    return _tool_catalog_rows()


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


@mcp.custom_route("/invoke", methods=["POST"])
async def invoke(request: Request) -> JSONResponse:
    body = await request.json()
    name = str(body.get("name") or "").strip()
    arguments = body.get("arguments") or {}
    if not name:
        return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
    if not isinstance(arguments, dict):
        return JSONResponse({"ok": False, "error": "arguments must be an object"}, status_code=400)
    owner = server_for_tool(name)
    requested = str(body.get("server") or "").strip()
    if requested and requested != owner:
        return JSONResponse(
            {"ok": False, "error": f"{name} is on server {owner}, not {requested}"},
            status_code=409,
        )
    try:
        result = dispatch_tool(name, arguments)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=404)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)
    return JSONResponse({"ok": True, "name": name, "server": owner, "result": result})


@mcp.custom_route("/servers", methods=["GET"])
async def servers(_request: Request) -> JSONResponse:
    return JSONResponse({"servers": orch_catalog()})


@mcp.custom_route("/pulse", methods=["GET"])
async def pulse(_request: Request) -> JSONResponse:
    return JSONResponse(pulse_state())
