"""Ephemeral agent workshop: definition + one user message → LLM result."""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.adapters.api.schemas import AgentWorkshopRunRequest, AgentWorkshopRunResponse
from app.application.agent_run import run_agent
from app.application.llm_catalog import generation_from_api
from app.core.deps import get_container, spawn_detached, visitor_id_header
from app.domain.agent_definition import AgentDefinition
from app.domain.analytics import AnalyticsEvent
from app.domain.entities import AUTO_MODEL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-workshop", tags=["agent-workshop"])


@router.post("/run", response_model=AgentWorkshopRunResponse)
async def run_workshop_agent(
    payload: AgentWorkshopRunRequest,
    request: Request,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> AgentWorkshopRunResponse:
    container = get_container(request)
    settings = container.settings
    visitor_key = client_visitor_id or "anonymous"
    container.agent_run_limiter.check_and_record(visitor_key)

    definition = AgentDefinition(
        name=(payload.definition.name or "").strip(),
        system_prompt=payload.definition.system_prompt,
        preferred_model=(payload.definition.preferred_model or AUTO_MODEL).strip()
        or AUTO_MODEL,
        temperature=payload.definition.temperature,
        max_tokens=payload.definition.max_tokens,
    )
    generation = generation_from_api(
        temperature=payload.definition.temperature,
        max_tokens=payload.definition.max_tokens,
        stop=None,
        prompt_format=False,
        prompt_length=False,
        prompt_stop=False,
        reasoning=False,
    )
    t0 = time.perf_counter()
    status = "ok"
    model_id = ""
    content = ""
    try:
        result = await run_agent(
            definition=definition,
            message=payload.message,
            router=container.router,
            enabled=settings.agents_run_enabled,
            max_message_chars=settings.max_message_chars,
            generation=generation,
        )
        content = result.content
        model_id = result.model_id
        return AgentWorkshopRunResponse(content=content, model_id=model_id)
    except Exception:
        status = "error"
        raise
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)

        async def _emit() -> None:
            try:
                name = (
                    "agent_run_completed" if status == "ok" else "agent_run_failed"
                )
                await container.analytics.capture(
                    [
                        AnalyticsEvent(
                            name=name,
                            distinct_id=visitor_key,
                            properties={
                                "status": status,
                                "model_id": model_id or None,
                                "preferred_model": definition.preferred_model,
                                "latency_ms": latency_ms,
                                "answer_chars": len(content),
                                "agent_name": definition.name or None,
                                "system_prompt_chars": len(definition.system_prompt or ""),
                                "message_chars": len(payload.message or ""),
                            },
                        )
                    ]
                )
            except Exception:  # noqa: BLE001 — analytics is fail-open
                logger.debug("agent_run analytics failed", exc_info=True)

        spawn_detached(_emit())
