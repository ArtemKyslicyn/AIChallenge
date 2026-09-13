"""Agent graph studio: run DAG of agents (SSE)."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.adapters.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, format_frame
from app.application.graph_run import iter_graph_run
from app.core.deps import get_container, visitor_id_header
from app.domain.errors import MessageValidationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-studio", tags=["agent-studio"])


class AgentStudioRunRequest(BaseModel):
    message: str = Field(default="", max_length=32_000)
    graph: dict[str, Any]


@router.post("/run")
async def run_agent_graph(
    payload: AgentStudioRunRequest,
    request: Request,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> StreamingResponse:
    container = get_container(request)
    settings = container.settings
    visitor = (client_visitor_id or "").strip() or "anonymous"
    container.agent_run_limiter.check_and_record(visitor)

    if not (payload.message or "").strip():
        raise MessageValidationError("Сообщение не должно быть пустым.")
    if not isinstance(payload.graph, dict):
        raise MessageValidationError("graph должен быть объектом.")

    async def frames():
        try:
            async for item in iter_graph_run(
                graph_payload=payload.graph,
                message=payload.message,
                router=container.router,
                enabled=settings.agents_run_enabled,
                max_message_chars=settings.max_message_chars,
            ):
                yield format_frame(item["event"], item["data"])
                if await request.is_disconnected():
                    break
        except MessageValidationError as exc:
            yield format_frame("error", {"message": str(exc)})
        except Exception as exc:  # noqa: BLE001
            logger.exception("agent graph run failed")
            yield format_frame("error", {"message": str(exc)[:500]})

    return StreamingResponse(frames(), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)
