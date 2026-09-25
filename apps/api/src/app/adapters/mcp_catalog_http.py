"""HTTP sidecar for MCP catalog, invoke, and pulse (Bearer). Not the wire protocol."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.domain.mcp_catalog import McpCatalog, McpPulseSnapshot, McpToolInfo


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _tool_info(item: dict[str, Any]) -> McpToolInfo | None:
    name = str(item.get("name") or "")
    if not name:
        return None
    params = item.get("parameters")
    return McpToolInfo(
        name=name,
        description=str(item.get("description") or ""),
        parameters=params if isinstance(params, dict) else None,
        server=str(item.get("server") or ""),
    )


class HttpMcpCatalog:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    async def fetch(self) -> McpCatalog:
        if not self._token:
            return McpCatalog(
                connected=False,
                protocol="mcp",
                server="",
                tools=(),
                error="MCP_SHARED_TOKEN unset",
            )
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{self._base}/catalog",
                    headers=_headers(self._token),
                )
        except httpx.HTTPError:
            return McpCatalog(
                connected=False,
                protocol="mcp",
                server="",
                tools=(),
                error="mcp unreachable",
            )
        if response.status_code != 200:
            return McpCatalog(
                connected=False,
                protocol="mcp",
                server="",
                tools=(),
                error=f"catalog HTTP {response.status_code}",
            )
        payload = response.json()
        tools = tuple(
            info
            for info in (_tool_info(item) for item in payload.get("tools") or [])
            if info is not None
        )
        return McpCatalog(
            connected=bool(payload.get("connected", True)),
            protocol=str(payload.get("protocol") or "mcp"),
            server=str(payload.get("server") or ""),
            tools=tools,
        )


class HttpMcpToolRunner:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._catalog = HttpMcpCatalog(base_url, token)
        self._servers: dict[str, str] = {}

    async def openai_tools(self) -> list[dict[str, object]]:
        catalog = await self._catalog.fetch()
        if not catalog.connected:
            return []
        self._servers = {tool.name: tool.server for tool in catalog.tools if tool.server}
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (
                        f"[{tool.server}] {tool.description}" if tool.server else tool.description
                    ),
                    "parameters": tool.parameters or {"type": "object", "properties": {}},
                },
            }
            for tool in catalog.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if not self._token:
            return '{"error":"MCP_SHARED_TOKEN unset"}'
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"{self._base}/invoke",
                    headers=_headers(self._token),
                    json={
                        "name": name,
                        "arguments": arguments or {},
                        "server": self._servers.get(name, ""),
                    },
                )
        except httpx.HTTPError as exc:
            return json_error("mcp unreachable", str(exc))
        if response.status_code != 200:
            return json_error(f"invoke HTTP {response.status_code}", response.text[:400])
        payload = response.json()
        if not payload.get("ok"):
            return json_error(str(payload.get("error") or "invoke failed"))
        return str(payload.get("result") or "")


class HttpMcpPulse:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    async def fetch(self) -> McpPulseSnapshot:
        if not self._token:
            return McpPulseSnapshot(jobs=(), latest_digest=None, error="MCP_SHARED_TOKEN unset")
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(
                    f"{self._base}/pulse",
                    headers=_headers(self._token),
                )
        except httpx.HTTPError:
            return McpPulseSnapshot(jobs=(), latest_digest=None, error="mcp unreachable")
        if response.status_code != 200:
            return McpPulseSnapshot(
                jobs=(),
                latest_digest=None,
                error=f"pulse HTTP {response.status_code}",
            )
        payload = response.json()
        jobs = tuple(item for item in (payload.get("jobs") or []) if isinstance(item, dict))
        digest = payload.get("latest_digest")
        watch = payload.get("watch")
        incidents = tuple(
            item for item in (payload.get("incidents") or []) if isinstance(item, dict)
        )
        action = payload.get("next_action")
        brief = payload.get("latest_brief")
        return McpPulseSnapshot(
            jobs=jobs,
            latest_digest=digest if isinstance(digest, dict) else None,
            latest_id=str(payload.get("latest_id") or "") or None,
            latest_at=str(payload.get("latest_at") or "") or None,
            watch=watch if isinstance(watch, dict) else None,
            incidents=incidents,
            next_action=action if isinstance(action, dict) else None,
            latest_brief=brief if isinstance(brief, dict) else None,
        )


def json_error(error: str, detail: str = "") -> str:
    body: dict[str, str] = {"error": error}
    if detail:
        body["detail"] = detail
    return json.dumps(body, ensure_ascii=False)


class FakeMcpCatalog:
    async def fetch(self) -> McpCatalog:
        return McpCatalog(
            connected=True,
            protocol="mcp",
            server="aichallenge-mcp",
            tools=(
                McpToolInfo("echo", "Return the given text unchanged."),
                McpToolInfo("time_now", "Current UTC time as ISO-8601."),
                McpToolInfo(
                    "list_stages",
                    "Task stages used on the stand: planning, execution, validation, done.",
                ),
                McpToolInfo(
                    "probe_stand",
                    "Live health of the stand API: /health status and latency in milliseconds.",
                    {"type": "object", "properties": {}},
                    "watch",
                ),
                McpToolInfo(
                    "model_pulse",
                    "Ranked model quality and down-votes over the last N hours.",
                    {
                        "type": "object",
                        "properties": {"hours": {"type": "integer", "default": 24}},
                    },
                    "models",
                ),
                McpToolInfo(
                    "schedule_digest",
                    "Schedule a recurring stand digest.",
                    {
                        "type": "object",
                        "properties": {
                            "interval_seconds": {"type": "integer", "default": 3600},
                            "hours": {"type": "integer", "default": 24},
                            "note": {"type": "string"},
                        },
                    },
                ),
                McpToolInfo(
                    "latest_digest",
                    "Most recent aggregated digest.",
                    {"type": "object", "properties": {}},
                ),
                McpToolInfo(
                    "list_jobs",
                    "Scheduled Pulse jobs.",
                    {"type": "object", "properties": {}},
                ),
                McpToolInfo(
                    "watch_brief",
                    "On-call brief: severity and open incidents.",
                    {"type": "object", "properties": {}},
                    "watch",
                ),
                McpToolInfo(
                    "ack_incident",
                    "Acknowledge an open watch incident.",
                    {
                        "type": "object",
                        "properties": {
                            "incident_id": {"type": "string"},
                            "note": {"type": "string"},
                        },
                    },
                ),
                McpToolInfo(
                    "probe_history",
                    "Recent /health probes from SQLite.",
                    {"type": "object", "properties": {"limit": {"type": "integer"}}},
                ),
                McpToolInfo(
                    "search",
                    "Collect stand facts for the night-brief pipeline.",
                    {"type": "object", "properties": {"hours": {"type": "integer"}}},
                    "brief",
                ),
                McpToolInfo(
                    "summarize",
                    "Turn search JSON into an operator brief.",
                    {"type": "object", "properties": {"payload": {"type": "string"}}},
                    "brief",
                ),
                McpToolInfo(
                    "saveToFile",
                    "Save the brief to disk and SQLite.",
                    {
                        "type": "object",
                        "properties": {
                            "brief": {"type": "string"},
                            "name": {"type": "string"},
                        },
                    },
                    "brief",
                ),
            ),
        )


class FakeMcpToolRunner:
    def __init__(self, result: str | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._result = result or (
            '{"ok":true,"latency_ms":12,"http_status":200,"payload":{"status":"ok"}}'
        )

    async def openai_tools(self) -> list[dict[str, object]]:
        catalog = await FakeMcpCatalog().fetch()
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (
                        f"[{tool.server}] {tool.description}" if tool.server else tool.description
                    ),
                    "parameters": tool.parameters or {"type": "object", "properties": {}},
                },
            }
            for tool in catalog.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        self.calls.append((name, dict(arguments or {})))
        if name == "search":
            return (
                '{"source":"search","health":{"ok":true,"latency_ms":12,'
                '"payload":{"status":"ok"}},"pulse":{"ranking":[]},"watch":{"severity":"ok"}}'
            )
        if name == "summarize":
            return (
                '{"source":"summarize","title":"Ночной бриф стенда",'
                '"body":"стенд жив, 12 мс","severity":"ok"}'
            )
        if name == "saveToFile":
            return '{"source":"saveToFile","path":"/tmp/night-brief.md","id":"brief-1","bytes":32}'
        return self._result
