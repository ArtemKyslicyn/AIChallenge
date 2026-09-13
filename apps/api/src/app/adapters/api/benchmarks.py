"""Public harness-bench leaderboard for connected models."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.application.benchmarks import (
    BoardWriteError,
    RefreshRateLimitedError,
    UpstreamFetchError,
    leaderboard_payload,
    refresh_board_from_upstream,
)
from app.core.deps import get_container
from app.domain.errors import BenchmarkRefreshError, MessageValidationError

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


@router.get("/leaderboard")
async def harness_leaderboard(request: Request) -> dict[str, Any]:
    container = get_container(request)
    settings = container.settings
    path = settings.benchmarks_board_path()
    if not path.is_file():
        raise MessageValidationError("Снимок бенчмарка не найден на сервере.")
    connected = [*settings.model_chain_list(), *settings.fallback_chain_list()]
    return leaderboard_payload(board_path=path, connected_model_ids=connected)


@router.post("/refresh")
async def refresh_harness_board(request: Request) -> dict[str, Any]:
    """Pull the latest README table from harness-bench-fast and rewrite the snapshot."""
    container = get_container(request)
    settings = container.settings
    path = settings.benchmarks_board_path()
    try:
        refresh_board_from_upstream(path, force=False)
    except RefreshRateLimitedError as exc:
        raise MessageValidationError(str(exc)) from exc
    except UpstreamFetchError as exc:
        raise BenchmarkRefreshError(str(exc)) from exc
    except BoardWriteError as exc:
        raise BenchmarkRefreshError(str(exc)) from exc
    except ValueError as exc:
        raise BenchmarkRefreshError(str(exc)) from exc

    connected = [*settings.model_chain_list(), *settings.fallback_chain_list()]
    payload = leaderboard_payload(board_path=path, connected_model_ids=connected)
    payload["refreshed"] = True
    return payload
