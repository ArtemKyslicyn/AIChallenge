"""Public harness-bench leaderboard for connected models."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app.application.benchmarks import leaderboard_payload
from app.core.deps import get_container
from app.domain.errors import MessageValidationError

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
