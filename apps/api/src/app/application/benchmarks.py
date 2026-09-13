"""Load harness-bench snapshot and build the connected-model leaderboard."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.domain.harness_bench import (
    HarnessBoard,
    LeaderboardEntry,
    build_leaderboard,
    parse_board,
)

logger = logging.getLogger(__name__)


def load_board(path: Path) -> HarnessBoard:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("harness board JSON must be an object")
    return parse_board(raw)


@lru_cache(maxsize=8)
def _cached_board(path_str: str, mtime_ns: int) -> HarnessBoard:
    return load_board(Path(path_str))


def get_board(path: Path) -> HarnessBoard:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"harness board not found: {resolved}")
    mtime_ns = resolved.stat().st_mtime_ns
    return _cached_board(str(resolved), mtime_ns)


def leaderboard_payload(
    *,
    board_path: Path,
    connected_model_ids: list[str],
) -> dict[str, Any]:
    board = get_board(board_path)
    entries = build_leaderboard(connected_model_ids, board)
    return {
        "task_set": board.task_set,
        "total_tasks": board.total_tasks,
        "source_url": board.source_url,
        "landing_url": board.landing_url,
        "updated_at": board.updated_at,
        "rows": [_entry_dict(e) for e in entries],
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
