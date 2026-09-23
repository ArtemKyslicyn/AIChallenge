"""Stand Pulse — live stand probes, SQLite jobs, periodic digests."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

MIN_INTERVAL = 30
MAX_INTERVAL = 86_400
DEFAULT_INTERVAL = 3_600
MAX_HOURS = 720
TICK_SECONDS = 5


def data_dir() -> Path:
    raw = os.environ.get("MCP_DATA_DIR", "").strip()
    path = Path(raw) if raw else Path(__file__).resolve().parents[2] / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "pulse.db"


def stand_api_url() -> str:
    return os.environ.get("STAND_API_URL", "http://127.0.0.1:8000").rstrip("/")


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _now_iso() -> str:
    return _now().isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            interval_seconds INTEGER NOT NULL,
            hours INTEGER NOT NULL DEFAULT 24,
            note TEXT NOT NULL DEFAULT '',
            due_at TEXT NOT NULL,
            last_run_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS digests (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            payload TEXT NOT NULL
        );
        """
    )
    conn.commit()
    return conn


def _get_json(url: str, timeout: float = 5.0) -> tuple[int, dict[str, Any] | None, int, str]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            latency = int((time.perf_counter() - started) * 1000)
            raw = response.read().decode("utf-8")
            body = json.loads(raw) if raw else {}
            if not isinstance(body, dict):
                body = {"value": body}
            return int(response.status), body, latency, ""
    except urllib.error.HTTPError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return int(exc.code), None, latency, str(exc)
    except Exception as exc:  # noqa: BLE001 — probe must never raise to the tool caller
        latency = int((time.perf_counter() - started) * 1000)
        return 0, None, latency, str(exc)


def build_probe() -> dict[str, Any]:
    url = f"{stand_api_url()}/api/v1/health"
    status, body, latency, error = _get_json(url)
    ok = status == 200 and (body or {}).get("status") == "ok"
    return {
        "ok": ok,
        "url": url,
        "http_status": status,
        "latency_ms": latency,
        "payload": body,
        "error": error or None,
        "checked_at": _now_iso(),
    }


def build_model_pulse(hours: int = 24) -> dict[str, Any]:
    window = max(1, min(int(hours), MAX_HOURS))
    base = stand_api_url()
    pareto_url = f"{base}/api/v1/lab/pareto?hours={window}"
    feedback_url = f"{base}/api/v1/lab/feedback-stats?hours={window}"
    p_status, pareto, p_ms, p_err = _get_json(pareto_url)
    f_status, feedback, f_ms, f_err = _get_json(feedback_url)
    ranking = list((pareto or {}).get("models") or [])[:8]
    attention = [
        row
        for row in list((feedback or {}).get("models") or [])
        if float(row.get("down_rate") or 0) >= 0.25 or bool(row.get("penalized"))
    ][:6]
    errors = [item for item in (p_err, f_err) if item]
    return {
        "hours": window,
        "checked_at": _now_iso(),
        "ranking": ranking,
        "attention": attention,
        "cascade": (pareto or {}).get("cascade"),
        "latency_ms": {"pareto": p_ms, "feedback": f_ms},
        "http_status": {"pareto": p_status, "feedback": f_status},
        "errors": errors,
    }


def _one_liner(health: dict[str, Any], pulse: dict[str, Any]) -> str:
    if health.get("ok"):
        line = f"стенд жив, {health.get('latency_ms')} мс"
    else:
        line = f"стенд не отвечает ({health.get('error') or health.get('http_status')})"
    ranking = pulse.get("ranking") or []
    if ranking:
        top = ranking[0]
        line += f"; лидер {top.get('model_id')} (score {top.get('score')})"
    attention = pulse.get("attention") or []
    if attention:
        line += f"; на внимании {attention[0].get('model_id')}"
    return line


def build_digest(hours: int = 24) -> dict[str, Any]:
    health = build_probe()
    pulse = build_model_pulse(hours)
    return {
        "generated_at": _now_iso(),
        "summary": _one_liner(health, pulse),
        "health": health,
        "pulse": pulse,
    }


def _clamp_interval(seconds: int) -> int:
    return max(MIN_INTERVAL, min(int(seconds), MAX_INTERVAL))


def schedule_digest_job(
    interval_seconds: int = DEFAULT_INTERVAL,
    hours: int = 24,
    note: str = "",
) -> dict[str, Any]:
    interval = _clamp_interval(interval_seconds)
    window = max(1, min(int(hours), MAX_HOURS))
    now = _now()
    job_id = str(uuid4())
    digest = build_digest(window)
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO jobs (
                id, kind, interval_seconds, hours, note, due_at, last_run_at, last_error, created_at
            ) VALUES (?, 'digest', ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                job_id,
                interval,
                window,
                (note or "").strip()[:200],
                (now + timedelta(seconds=interval)).isoformat(),
                now.isoformat(),
                now.isoformat(),
            ),
        )
        conn.execute(
            "INSERT INTO digests (id, created_at, payload) VALUES (?, ?, ?)",
            (str(uuid4()), now.isoformat(), json.dumps(digest, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "job_id": job_id,
        "kind": "digest",
        "interval_seconds": interval,
        "hours": window,
        "note": (note or "").strip()[:200],
        "next_run": (now + timedelta(seconds=interval)).isoformat(),
        "first_digest": digest,
    }


def list_jobs_payload() -> dict[str, Any]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, interval_seconds, hours, note, due_at, last_run_at, last_error, created_at "
            "FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    finally:
        conn.close()
    jobs = [
        {
            "id": row["id"],
            "kind": row["kind"],
            "interval_seconds": row["interval_seconds"],
            "hours": row["hours"],
            "note": row["note"],
            "due_at": row["due_at"],
            "last_run_at": row["last_run_at"],
            "last_error": row["last_error"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {"jobs": jobs, "count": len(jobs)}


def latest_digest_payload() -> dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, created_at, payload FROM digests ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"digest": None, "message": "сводок ещё нет — поставьте schedule_digest"}
    payload = json.loads(row["payload"])
    return {"id": row["id"], "created_at": row["created_at"], "digest": payload}


def process_due_jobs(now: datetime | None = None) -> int:
    moment = (now or _now()).replace(microsecond=0)
    stamp = moment.isoformat()
    conn = _connect()
    ran = 0
    try:
        rows = conn.execute(
            "SELECT id, interval_seconds, hours FROM jobs WHERE due_at <= ?",
            (stamp,),
        ).fetchall()
        for row in rows:
            try:
                digest = build_digest(int(row["hours"]))
                conn.execute(
                    "INSERT INTO digests (id, created_at, payload) VALUES (?, ?, ?)",
                    (str(uuid4()), stamp, json.dumps(digest, ensure_ascii=False)),
                )
                nxt = (moment + timedelta(seconds=int(row["interval_seconds"]))).isoformat()
                conn.execute(
                    "UPDATE jobs SET last_run_at = ?, last_error = NULL, due_at = ? WHERE id = ?",
                    (stamp, nxt, row["id"]),
                )
                ran += 1
            except Exception as exc:  # noqa: BLE001
                nxt = (moment + timedelta(seconds=int(row["interval_seconds"]))).isoformat()
                conn.execute(
                    "UPDATE jobs SET last_error = ?, due_at = ? WHERE id = ?",
                    (str(exc)[:300], nxt, row["id"]),
                )
        conn.commit()
    finally:
        conn.close()
    return ran


async def run_scheduler() -> None:
    import asyncio

    while True:
        try:
            process_due_jobs()
        except Exception:
            pass
        await asyncio.sleep(TICK_SECONDS)


def pulse_state() -> dict[str, Any]:
    latest = latest_digest_payload()
    jobs = list_jobs_payload()
    return {
        "jobs": jobs["jobs"],
        "latest_digest": latest.get("digest"),
        "latest_id": latest.get("id"),
        "latest_at": latest.get("created_at"),
    }
