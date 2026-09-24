"""Stand Pulse: persist jobs, first digest, due-job tick, tool schemas."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aichallenge_mcp.pulse import (
    ack_incident,
    archive_brief,
    build_probe,
    collect_stand,
    compose_brief,
    latest_brief_payload,
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
    assert "hours" in tools["search"].parameters["properties"]
    assert "payload" in tools["summarize"].parameters["properties"]
    assert "brief" in tools["saveToFile"].parameters["properties"]


def test_pipeline_search_summarize_save(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MCP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("STAND_API_URL", "http://127.0.0.1:9")
    collected = collect_stand(hours=6)
    assert collected["source"] == "search"
    assert collected["hours"] == 6
    assert "health" in collected
    summarized = compose_brief(json.dumps(collected, ensure_ascii=False))
    assert summarized["source"] == "summarize"
    assert summarized["from"] == "search"
    assert summarized["title"]
    assert "стенд" in summarized["body"]
    saved = archive_brief(json.dumps(summarized, ensure_ascii=False), name="night-brief")
    assert saved["source"] == "saveToFile"
    assert saved["from"] == "summarize"
    path = Path(saved["path"])
    assert path.is_file()
    assert "Ночной бриф" in path.read_text(encoding="utf-8")
    latest = latest_brief_payload()
    assert latest["id"] == saved["id"]
    via_dispatch = json.loads(dispatch_tool("search", {"hours": 6}))
    assert via_dispatch["source"] == "search"
