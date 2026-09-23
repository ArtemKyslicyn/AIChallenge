"""Stand Pulse: persist jobs, first digest, due-job tick, tool schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aichallenge_mcp.pulse import (
    latest_digest_payload,
    list_jobs_payload,
    process_due_jobs,
    schedule_digest_job,
)
from aichallenge_mcp.server import PULSE_TOOL_NAMES, dispatch_tool, mcp


def test_schedule_writes_sqlite_and_first_digest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STAND_API_URL", "http://127.0.0.1:9")
    scheduled = schedule_digest_job(interval_seconds=60, hours=24, note="ops")
    assert scheduled["job_id"]
    assert scheduled["interval_seconds"] == 60
    assert scheduled["first_digest"]["summary"]
    jobs = list_jobs_payload()
    assert jobs["count"] == 1
    latest = latest_digest_payload()
    assert latest["digest"]["health"]["ok"] is False


def test_due_jobs_write_another_digest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STAND_API_URL", "http://127.0.0.1:9")
    schedule_digest_job(interval_seconds=30, hours=6, note="tick")
    future = datetime.now(UTC).replace(microsecond=0) + timedelta(hours=1)
    assert process_due_jobs(future) == 1
    conn_jobs = list_jobs_payload()["jobs"]
    assert conn_jobs[0]["last_run_at"]


def test_dispatch_unknown_tool() -> None:
    try:
        dispatch_tool("nope")
    except ValueError as exc:
        assert "unknown" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_pulse_tools_have_parameter_schemas() -> None:
    tools = {tool.name: tool for tool in getattr(mcp, "_tool_manager").list_tools()}
    assert PULSE_TOOL_NAMES <= set(tools)
    schema = tools["model_pulse"].parameters
    assert schema["properties"]["hours"]["type"] == "integer"
    sched = tools["schedule_digest"].parameters
    assert "interval_seconds" in sched["properties"]
    assert "hours" in sched["properties"]
