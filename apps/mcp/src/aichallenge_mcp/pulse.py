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
HIGH_LATENCY_MS = 800
DOWN_RATE_LIMIT = 0.25


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
        CREATE TABLE IF NOT EXISTS probes (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            ok INTEGER NOT NULL,
            latency_ms INTEGER,
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            key TEXT NOT NULL,
            severity TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT NOT NULL,
            opened_at TEXT NOT NULL,
            resolved_at TEXT,
            acked_at TEXT,
            ack_note TEXT
        );
        CREATE TABLE IF NOT EXISTS briefs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            path TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
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


def build_probe(*, persist: bool = True) -> dict[str, Any]:
    url = f"{stand_api_url()}/api/v1/health"
    status, body, latency, error = _get_json(url)
    ok = status == 200 and (body or {}).get("status") == "ok"
    result = {
        "ok": ok,
        "url": url,
        "http_status": status,
        "latency_ms": latency,
        "payload": body,
        "error": error or None,
        "checked_at": _now_iso(),
    }
    if persist:
        _store_probe(result)
        evaluate_watch(health=result, pulse=None)
    return result


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
    health = build_probe(persist=True)
    pulse = build_model_pulse(hours)
    evaluate_watch(health=health, pulse=pulse)
    brief = watch_brief()
    return {
        "generated_at": _now_iso(),
        "summary": brief.get("summary") or _one_liner(health, pulse),
        "health": health,
        "pulse": pulse,
        "watch": brief,
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


def _store_probe(health: dict[str, Any]) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO probes (id, created_at, ok, latency_ms, payload) VALUES (?, ?, ?, ?, ?)",
            (
                str(uuid4()),
                health.get("checked_at") or _now_iso(),
                1 if health.get("ok") else 0,
                health.get("latency_ms"),
                json.dumps(health, ensure_ascii=False),
            ),
        )
        conn.execute(
            "DELETE FROM probes WHERE id NOT IN (SELECT id FROM probes ORDER BY created_at DESC LIMIT 200)"
        )
        conn.commit()
    finally:
        conn.close()


def _open_incident(kind: str, key: str, severity: str, title: str, detail: str) -> None:
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT id FROM incidents WHERE key = ? AND resolved_at IS NULL",
            (key,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE incidents SET detail = ?, severity = ?, title = ? WHERE id = ?",
                (detail[:500], severity, title[:200], existing["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO incidents (
                    id, kind, key, severity, title, detail, opened_at, resolved_at, acked_at, ack_note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (str(uuid4()), kind, key, severity, title[:200], detail[:500], _now_iso()),
            )
        conn.commit()
    finally:
        conn.close()


def _resolve_incident(key: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE incidents SET resolved_at = ? WHERE key = ? AND resolved_at IS NULL",
            (_now_iso(), key),
        )
        conn.commit()
    finally:
        conn.close()


def evaluate_watch(
    *,
    health: dict[str, Any],
    pulse: dict[str, Any] | None,
) -> None:
    if not health.get("ok"):
        _open_incident(
            "stand_down",
            "stand_down",
            "critical",
            "Стенд не отвечает",
            str(health.get("error") or health.get("http_status") or "down"),
        )
        _resolve_incident("high_latency")
    else:
        _resolve_incident("stand_down")
        latency = int(health.get("latency_ms") or 0)
        if latency >= HIGH_LATENCY_MS:
            _open_incident(
                "high_latency",
                "high_latency",
                "warning",
                "Высокая задержка /health",
                f"{latency} мс (порог {HIGH_LATENCY_MS})",
            )
        else:
            _resolve_incident("high_latency")
    if pulse is None:
        return
    live_keys: set[str] = set()
    for row in pulse.get("attention") or []:
        model_id = str(row.get("model_id") or "").strip()
        if not model_id:
            continue
        key = f"model:{model_id}"
        live_keys.add(key)
        rate = row.get("down_rate")
        _open_incident(
            "model_attention",
            key,
            "warning",
            f"Модель на внимании: {model_id}",
            f"down_rate={rate} penalized={row.get('penalized')}",
        )
    conn = _connect()
    try:
        open_models = conn.execute(
            "SELECT key FROM incidents WHERE kind = 'model_attention' AND resolved_at IS NULL"
        ).fetchall()
        for row in open_models:
            if row["key"] not in live_keys:
                _resolve_incident(row["key"])
    finally:
        conn.close()


def list_open_incidents() -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, kind, key, severity, title, detail, opened_at, acked_at, ack_note "
            "FROM incidents WHERE resolved_at IS NULL ORDER BY opened_at DESC"
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": row["id"],
            "kind": row["kind"],
            "key": row["key"],
            "severity": row["severity"],
            "title": row["title"],
            "detail": row["detail"],
            "opened_at": row["opened_at"],
            "acked": bool(row["acked_at"]),
            "ack_note": row["ack_note"],
        }
        for row in rows
    ]


def ack_incident(incident_id: str, note: str = "") -> dict[str, Any]:
    ident = (incident_id or "").strip()
    if not ident:
        return {"ok": False, "error": "incident_id required"}
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id FROM incidents WHERE id = ? AND resolved_at IS NULL",
            (ident,),
        ).fetchone()
        if row is None:
            return {"ok": False, "error": "open incident not found"}
        conn.execute(
            "UPDATE incidents SET acked_at = ?, ack_note = ? WHERE id = ?",
            (_now_iso(), (note or "").strip()[:200], ident),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "incident_id": ident, "acked": True}


def probe_history(limit: int = 12) -> dict[str, Any]:
    cap = max(1, min(int(limit), 50))
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT created_at, ok, latency_ms FROM probes ORDER BY created_at DESC LIMIT ?",
            (cap,),
        ).fetchall()
    finally:
        conn.close()
    items = [
        {"at": row["created_at"], "ok": bool(row["ok"]), "latency_ms": row["latency_ms"]}
        for row in rows
    ]
    return {"probes": items, "count": len(items)}


def watch_brief() -> dict[str, Any]:
    incidents = list_open_incidents()
    history = probe_history(8)
    probes = history["probes"]
    latest = probes[0] if probes else None
    previous = probes[1] if len(probes) > 1 else None
    if any(item["severity"] == "critical" and not item["acked"] for item in incidents):
        severity = "critical"
    elif incidents:
        severity = "warning"
    else:
        severity = "ok"
    if severity == "critical":
        summary = "вахта: стенд недоступен"
    elif severity == "warning":
        summary = f"вахта: {len(incidents)} открытых инцидента"
    elif latest and latest.get("ok"):
        summary = f"вахта спокойна, {latest.get('latency_ms')} мс"
    else:
        summary = "вахта спокойна, пробы ещё нет"
    delta = None
    if latest and previous and latest.get("latency_ms") is not None and previous.get("latency_ms") is not None:
        delta = int(latest["latency_ms"]) - int(previous["latency_ms"])
    action = recommend_action(severity, incidents, jobs_count=list_jobs_payload()["count"])
    return {
        "severity": severity,
        "summary": summary,
        "open_incidents": incidents,
        "open_count": len(incidents),
        "latest_probe": latest,
        "latency_delta_ms": delta,
        "probes": probes,
        "next_action": action,
    }


def recommend_action(
    severity: str,
    incidents: list[dict[str, Any]],
    *,
    jobs_count: int,
) -> dict[str, Any]:
    """What the operator should do now — the product, not the tool list."""
    unacked = [item for item in incidents if not item.get("acked")]
    if severity == "critical":
        return {
            "id": "stand_down",
            "title": "Стенд не отвечает",
            "detail": "Посетители не получат ответ модели. Вахта уже открыла инцидент — проверьте API.",
            "cta": "probe",
        }
    if unacked:
        first = unacked[0]
        return {
            "id": "ack",
            "title": "Есть неподтверждённый инцидент",
            "detail": str(first.get("title") or "нужно подтверждение"),
            "cta": "ack",
            "incident_id": first.get("id"),
        }
    if jobs_count < 1:
        return {
            "id": "schedule",
            "title": "Ночная вахта выключена",
            "detail": "Пока никого нет у экрана, сводки не пишутся. Включите ежечасный обход.",
            "cta": "schedule",
        }
    return {
        "id": "ok",
        "title": "Можно отойти",
        "detail": "Health жив, открытых тревог нет, сводка идёт по расписанию.",
        "cta": None,
    }


def collect_stand(hours: int = 24) -> dict[str, Any]:
    """Search step: pull live stand facts for the next tool."""
    window = max(1, min(int(hours), MAX_HOURS))
    health = build_probe(persist=True)
    pulse = build_model_pulse(window)
    evaluate_watch(health=health, pulse=pulse)
    return {
        "source": "search",
        "hours": window,
        "collected_at": _now_iso(),
        "health": health,
        "pulse": pulse,
        "watch": watch_brief(),
    }


def _parse_payload(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {"body": text}
        else:
            return {"body": text}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def compose_brief(payload: str) -> dict[str, Any]:
    """Summarize step: turn search JSON into an operator brief."""
    data = _parse_payload(payload)
    health = data.get("health") if isinstance(data.get("health"), dict) else {}
    pulse = data.get("pulse") if isinstance(data.get("pulse"), dict) else {}
    watch = data.get("watch") if isinstance(data.get("watch"), dict) else {}
    ranking = list(pulse.get("ranking") or [])
    top = ranking[0] if ranking else {}
    incidents = list(watch.get("open_incidents") or [])
    if health.get("ok"):
        lead = f"стенд жив, {health.get('latency_ms')} мс"
    else:
        lead = f"стенд не отвечает ({health.get('error') or health.get('http_status')})"
    if top.get("model_id"):
        lead += f"; лидер {top.get('model_id')}"
    if incidents:
        lead += f"; инцидентов {len(incidents)}"
    title = "Ночной бриф стенда"
    body = "\n".join(
        [
            f"# {title}",
            "",
            lead,
            "",
            f"severity: {watch.get('severity') or 'unknown'}",
            f"next: {(watch.get('next_action') or {}).get('title') or '—'}",
        ]
    )
    return {
        "source": "summarize",
        "title": title,
        "body": body,
        "severity": watch.get("severity") or ("ok" if health.get("ok") else "critical"),
        "from": data.get("source") or "search",
        "composed_at": _now_iso(),
    }


def archive_brief(brief: str, name: str = "night-brief") -> dict[str, Any]:
    """saveToFile step: persist the summarized brief to disk and SQLite."""
    data = _parse_payload(brief)
    title = str(data.get("title") or name or "night-brief")
    body = str(data.get("body") or brief)
    stamp = _now().strftime("%Y%m%dT%H%M%SZ")
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in (name or "brief"))[:40]
    folder = data_dir() / "briefs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{stamp}-{slug}.md"
    path.write_text(body + "\n", encoding="utf-8")
    ident = str(uuid4())
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO briefs (id, created_at, path, title, payload) VALUES (?, ?, ?, ?, ?)",
            (ident, _now_iso(), str(path), title[:200], json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "source": "saveToFile",
        "id": ident,
        "path": str(path),
        "title": title,
        "bytes": path.stat().st_size,
        "from": data.get("source") or "summarize",
        "saved_at": _now_iso(),
    }


def latest_brief_payload() -> dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, created_at, path, title FROM briefs ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return {"brief": None}
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "path": row["path"],
        "title": row["title"],
    }


def pulse_state() -> dict[str, Any]:
    latest = latest_digest_payload()
    jobs = list_jobs_payload()
    brief = watch_brief()
    archived = latest_brief_payload()
    return {
        "jobs": jobs["jobs"],
        "latest_digest": latest.get("digest"),
        "latest_id": latest.get("id"),
        "latest_at": latest.get("created_at"),
        "watch": brief,
        "incidents": brief["open_incidents"],
        "next_action": brief.get("next_action"),
        "latest_brief": archived if archived.get("id") else None,
    }
