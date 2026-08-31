"""Direct LLM probe. Same provider and router as chat; nothing is persisted."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.adapters.api.schemas import ProbeRequest, ProbeResponse
from app.adapters.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, format_frame
from app.application.llm_probe import complete_probe
from app.core.deps import get_container
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import MessageValidationError, ProbeDisabledError

router = APIRouter(prefix="/llm", tags=["llm"])


def _turns(payload: ProbeRequest) -> list[ChatMessage]:
    if payload.messages:
        return [ChatMessage(role=MessageRole(m.role), content=m.content) for m in payload.messages]
    if payload.prompt and payload.prompt.strip():
        return [ChatMessage(role=MessageRole.USER, content=payload.prompt)]
    raise MessageValidationError("Передайте либо «prompt», либо «messages».")


@router.post("/complete", response_model=None)
async def complete(payload: ProbeRequest, request: Request) -> ProbeResponse | StreamingResponse:
    container = get_container(request)
    enabled = container.settings.llm_probe_enabled
    turns = _turns(payload)

    if not payload.stream:
        result = await complete_probe(
            router=container.router, messages=turns, preferred_model=payload.model, enabled=enabled
        )
        return ProbeResponse(content=result.content, model_id=result.model_id)

    if not enabled:
        raise ProbeDisabledError("Probe к модели отключён конфигурацией.")

    async def frames() -> AsyncIterator[str]:
        model_id: str | None = None
        parts: list[str] = []
        async for chunk in container.router.stream_chat(turns, preferred_model=payload.model):
            if chunk.model_id != model_id:
                model_id = chunk.model_id
                yield format_frame("model", {"model_id": model_id})
            parts.append(chunk.text)
            yield format_frame("token", {"text": chunk.text})
        # message_id is null: a probe is never persisted, so there is no id to
        # report. The frame shape stays the same so one client parser works.
        yield format_frame(
            "message_end",
            {"message_id": None, "content": "".join(parts), "model_id": model_id},
        )

    return StreamingResponse(frames(), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)
