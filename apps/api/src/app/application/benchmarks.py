"""Load / refresh harness-bench snapshot and build leaderboards."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.harness_bench import (
    HarnessBoard,
    LeaderboardEntry,
    build_leaderboard,
    match_board_row,
    parse_board,
)

logger = logging.getLogger(__name__)

README_URL = "https://raw.githubusercontent.com/ai-forever/harness-bench-fast/main/README.md"
SOURCE = "https://github.com/ai-forever/harness-bench-fast"
LANDING = "https://ai-forever.github.io/harness-bench-fast/"

#: Minimum seconds between successful upstream refreshes (button + cron).
REFRESH_COOLDOWN_SECONDS = 60

_last_refresh_mono: float = 0.0


def load_board(path: Path) -> HarnessBoard:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("harness board JSON must be an object")
    return parse_board(raw)


@lru_cache(maxsize=8)
def _cached_board(path_str: str, mtime_ns: int) -> HarnessBoard:
    return load_board(Path(path_str))


def clear_board_cache() -> None:
    _cached_board.cache_clear()


def get_board(path: Path) -> HarnessBoard:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"harness board not found: {resolved}")
    mtime_ns = resolved.stat().st_mtime_ns
    return _cached_board(str(resolved), mtime_ns)


def fetch_readme_text(*, timeout: float = 45.0) -> str:
    req = urllib.request.Request(
        README_URL,
        headers={"User-Agent": "aichallenge-harness-board-sync/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if isinstance(raw, bytes):
            return raw.decode("utf-8")
        return bytes(raw).decode("utf-8")


def parse_readme_rows(text: str) -> list[dict[str, Any]]:
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        if line.startswith("| Harness") and "Result" in line:
            start = i
            break
    if start is None:
        raise ValueError("harness-bench README table not found")

    rows: list[dict[str, Any]] = []
    for line in lines[start + 2 :]:
        if not line.startswith("|"):
            break
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 7:
            continue
        harness, profile, model, result, pct, steps, tokens = parts[:7]
        match = re.match(r"(\d+)\s*/\s*(\d+)", result.replace(",", ""))
        if not match:
            continue
        passed, total = int(match.group(1)), int(match.group(2))
        pct_match = re.match(r"([\d.]+)\s*%", pct.replace(",", ""))
        pct_f = float(pct_match.group(1)) if pct_match else round(100.0 * passed / total, 1)
        rows.append(
            {
                "harness": harness,
                "profile": None if profile in {"—", "-"} else profile,
                "model_label": model,
                "passed": passed,
                "total": total,
                "pct": pct_f,
                "steps": _num(steps),
                "tokens": _num(tokens),
                "source": SOURCE,
            }
        )
    if not rows:
        raise ValueError("no leaderboard rows parsed from README")
    return rows


def board_dict_from_readme(text: str) -> dict[str, Any]:
    rows = parse_readme_rows(text)
    total_tasks = max((int(r["total"]) for r in rows), default=391)
    return {
        "task_set": "v0.16.0",
        "total_tasks": total_tasks,
        "source_url": SOURCE,
        "landing_url": LANDING,
        "updated_at": datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": rows,
    }


def write_board(path: Path, board: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    clear_board_cache()


def refresh_board_from_upstream(path: Path, *, force: bool = False) -> dict[str, Any]:
    """Fetch README, write snapshot, return leaderboard meta for the new board."""
    global _last_refresh_mono
    now = time.monotonic()
    if not force and _last_refresh_mono and (now - _last_refresh_mono) < REFRESH_COOLDOWN_SECONDS:
        wait = int(REFRESH_COOLDOWN_SECONDS - (now - _last_refresh_mono))
        raise RefreshRateLimitedError(f"Подождите {wait} с перед следующим обновлением.")

    try:
        text = fetch_readme_text()
    except urllib.error.URLError as exc:
        raise UpstreamFetchError(f"Не удалось скачать README: {exc}") from exc

    payload = board_dict_from_readme(text)
    try:
        write_board(path, payload)
    except OSError as exc:
        raise BoardWriteError(f"Не удалось записать снимок: {exc}") from exc

    _last_refresh_mono = time.monotonic()
    logger.info(
        "harness board refreshed rows=%s updated_at=%s path=%s",
        len(payload["rows"]),
        payload["updated_at"],
        path,
    )
    return payload


def leaderboard_payload(
    *,
    board_path: Path,
    connected_model_ids: list[str],
) -> dict[str, Any]:
    board = get_board(board_path)
    chain_entries = build_leaderboard(connected_model_ids, board)
    matched = sum(1 for e in chain_entries if e.matched)

    links: dict[tuple[str, str | None, str, int], list[str]] = {}
    for mid in connected_model_ids:
        hit = match_board_row(mid, board)
        if hit is None:
            continue
        key = (hit.harness, hit.profile, hit.model_label, hit.passed)
        links.setdefault(key, []).append(mid)

    full_board: list[dict[str, Any]] = []
    for idx, row in enumerate(board.rows, start=1):
        key = (row.harness, row.profile, row.model_label, row.passed)
        linked = links.get(key, [])
        full_board.append(
            {
                "rank": idx,
                "harness": row.harness,
                "profile": row.profile,
                "model_label": row.model_label,
                "passed": row.passed,
                "total": row.total,
                "pct": row.pct,
                "steps": row.steps,
                "tokens": row.tokens,
                "in_chain": bool(linked),
                "linked_model_ids": linked,
            }
        )

    return {
        "task_set": board.task_set,
        "total_tasks": board.total_tasks,
        "source_url": board.source_url,
        "landing_url": board.landing_url,
        "updated_at": board.updated_at,
        "coverage": {
            "connected": len(chain_entries),
            "matched": matched,
            "unmatched": len(chain_entries) - matched,
            "board_rows": len(board.rows),
        },
        "rows": [_entry_dict(e) for e in chain_entries],
        "board": full_board,
    }


def _entry_dict(entry: LeaderboardEntry) -> dict[str, Any]:
    return {
        "rank": entry.rank,
        "model_id": entry.model_id,
        "model_label": entry.model_label,
        "harness": entry.harness,
        "profile": entry.profile,
        "passed": entry.passed,
        "total": entry.total,
        "pct": entry.pct,
        "steps": entry.steps,
        "tokens": entry.tokens,
        "in_chain": entry.in_chain,
        "matched": entry.matched,
    }


def _num(raw: str) -> int | None:
    text = raw.strip().replace(",", "")
    if text in {"", "-", "—", "–"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


class RefreshRateLimitedError(Exception):
    pass


class UpstreamFetchError(Exception):
    pass


class BoardWriteError(Exception):
    pass
