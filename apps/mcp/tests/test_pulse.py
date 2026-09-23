"""Stand Pulse: persist jobs, first digest, due-job tick, tool schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aichallenge_mcp.pulse import (
    ack_incident,
    build_probe,
    latest_digest_payload,
    list_jobs_payload,
    process_due_jobs,
    recommend_action,
    schedule_digest_job,
    watch_brief,
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


def test_watch_opens_and_acks_stand_down(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STAND_API_URL", "http://127.0.0.1:9")
    health = build_probe()
    assert health["ok"] is False
    brief = watch_brief()
    assert brief["severity"] == "critical"
    assert brief["open_count"] >= 1
    incident_id = brief["open_incidents"][0]["id"]
    acked = ack_incident(incident_id, "seen")
    assert acked["ok"] is True
    after = watch_brief()
    assert after["open_incidents"][0]["acked"] is True


def test_recommend_action_is_the_operator_job() -> None:
    down = recommend_action("critical", [], jobs_count=0)
    assert down["cta"] == "probe"
    unacked = recommend_action(
        "warning",
        [{"id": "inc-1", "title": "Модель на внимании", "acked": False}],
        jobs_count=2,
    )
    assert unacked["cta"] == "ack"
    assert unacked["incident_id"] == "inc-1"
    night = recommend_action("ok", [], jobs_count=0)
    assert night["cta"] == "schedule"
    calm = recommend_action("ok", [], jobs_count=1)
    assert calm["id"] == "ok"
    assert calm["cta"] is None


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
