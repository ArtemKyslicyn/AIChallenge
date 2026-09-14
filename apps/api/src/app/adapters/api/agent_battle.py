"""Agent battle sandbox: competing personas over SSE."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.adapters.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, format_frame
from app.application.battle_run import iter_battle_run
from app.core.deps import get_container, visitor_id_header
from app.domain.errors import DomainError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-battle", tags=["agent-battle"])


class AgentBattleRunRequest(BaseModel):
    arena: dict[str, Any] = Field(default_factory=dict)


@router.post("/run")
async def run_agent_battle(
    payload: AgentBattleRunRequest,
    request: Request,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> StreamingResponse:
    container = get_container(request)
    settings = container.settings
    visitor = (client_visitor_id or "").strip() or "anonymous"
    container.agent_run_limiter.check_and_record(visitor)

    if not isinstance(payload.arena, dict):
        raise DomainError("arena must be an object")

    async def frames() -> AsyncIterator[str]:
        try:
            async for item in iter_battle_run(
                arena_payload=payload.arena,
                router=container.router,
                enabled=settings.agents_battle_enabled and settings.agents_run_enabled,
                max_rounds_cap=8,
                default_rounds=settings.battle_max_rounds,
            ):
                yield format_frame(item["event"], item["data"])
                if await request.is_disconnected():
                    break
        except DomainError as exc:
            yield format_frame("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent battle failed")
            yield format_frame("error", {"message": str(exc)[:500]})

    return StreamingResponse(frames(), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)
