"""Agent battle sandbox: competing personas over SSE."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.adapters.api.auth import OptionalAuthUser
from app.adapters.api.local_llm import load_user_source
from app.adapters.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, format_frame
from app.application.battle_run import iter_battle_run
from app.application.local_llm import local_llm_scope
from app.application.local_llm_rate_limit import charge_local_pin
from app.core.deps import get_container, visitor_id_header
from app.domain.errors import DomainError
from app.domain.local_llm import LOCAL_LLM_PREFIX

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-battle", tags=["agent-battle"])


class AgentBattleRunRequest(BaseModel):
    arena: dict[str, Any] = Field(default_factory=dict)


@router.post("/run")
def _arena_models(arena: dict[str, Any]) -> list[str]:
    models: list[str] = []
    for item in arena.get("cast") or []:
        if not isinstance(item, dict):
            continue
        model = str(item.get("preferred_model") or item.get("preferredModel") or "")
        if model.startswith(LOCAL_LLM_PREFIX):
            models.append(model)
    return models


async def run_agent_battle(
    payload: AgentBattleRunRequest,
    request: Request,
    auth_user: OptionalAuthUser,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> StreamingResponse:
    container = get_container(request)
    settings = container.settings
    visitor = (client_visitor_id or "").strip() or "anonymous"
    container.agent_run_limiter.check_and_record(visitor)

    if not isinstance(payload.arena, dict):
        raise DomainError("arena must be an object")
    charge_local_pin(
        container.local_llm_limiter,
        user_id=None if auth_user is None else auth_user.id,
        models=_arena_models(payload.arena),
    )
    source = await load_user_source(request, auth_user)

    async def frames() -> AsyncIterator[str]:
        try:
            async with local_llm_scope(source):
                async for item in iter_battle_run(
                    arena_payload=payload.arena,
                    router=container.router,
                    enabled=settings.agents_battle_enabled and settings.agents_run_enabled,
                    max_rounds_cap=16,
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
