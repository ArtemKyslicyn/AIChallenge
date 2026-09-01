"""Direct LLM probe and model catalog."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.adapters.api.schemas import (
    ModelCapabilitiesResponse,
    ModelCatalogItemResponse,
    ProbeRequest,
    ProbeResponse,
)
from app.adapters.api.sse import SSE_HEADERS, SSE_MEDIA_TYPE, format_frame
from app.application.llm_catalog import generation_from_api, list_model_catalog
from app.application.llm_probe import complete_probe
from app.core.deps import get_container
from app.domain.entities import ChatMessage, MessageRole
from app.domain.errors import MessageValidationError, ProbeDisabledError
from app.domain.generation import apply_generation_to_messages

router = APIRouter(prefix="/llm", tags=["llm"])


def _turns(payload: ProbeRequest) -> list[ChatMessage]:
    if payload.messages:
        return [ChatMessage(role=MessageRole(m.role), content=m.content) for m in payload.messages]
    if payload.prompt and payload.prompt.strip():
        return [ChatMessage(role=MessageRole.USER, content=payload.prompt)]
    raise MessageValidationError("Передайте либо «prompt», либо «messages».")


def _generation(payload: ProbeRequest):
    return generation_from_api(
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        stop=payload.stop,
        prompt_format=payload.prompt_format,
        prompt_length=payload.prompt_length,
        prompt_stop=payload.prompt_stop,
        reasoning=payload.reasoning,
    )


@router.get("/models", response_model=list[ModelCatalogItemResponse])
async def models(request: Request) -> list[ModelCatalogItemResponse]:
    container = get_container(request)
    settings = container.settings
    model_ids = [*settings.model_chain_list(), *settings.fallback_chain_list()]
    return [
        ModelCatalogItemResponse(
            id=entry.id,
            label=entry.label,
            capabilities=ModelCapabilitiesResponse(
                temperature=entry.capabilities.temperature,
                max_tokens=entry.capabilities.max_tokens,
                stop=entry.capabilities.stop,
                reasoning=entry.capabilities.reasoning,
            ),
        )
        for entry in list_model_catalog(model_ids)
    ]


@router.post("/complete", response_model=None)
async def complete(payload: ProbeRequest, request: Request) -> ProbeResponse | StreamingResponse:
    container = get_container(request)
    enabled = container.settings.llm_probe_enabled
    turns = _turns(payload)
    generation = _generation(payload)

    if not payload.stream:
        result = await complete_probe(
            router=container.router,
            messages=turns,
            preferred_model=payload.model,
            enabled=enabled,
            generation=generation,
        )
        return ProbeResponse(content=result.content, model_id=result.model_id)

    if not enabled:
        raise ProbeDisabledError("Probe к модели отключён конфигурацией.")

    prepared = apply_generation_to_messages(turns, generation)

    async def frames() -> AsyncIterator[str]:
        model_id: str | None = None
        parts: list[str] = []
        async for chunk in container.router.stream_chat(
            prepared, preferred_model=payload.model, generation=generation
        ):
            if chunk.model_id != model_id:
                model_id = chunk.model_id
                yield format_frame("model", {"model_id": model_id})
            parts.append(chunk.text)
            yield format_frame("token", {"text": chunk.text})
        yield format_frame(
            "message_end",
            {"message_id": None, "content": "".join(parts), "model_id": model_id},
        )

    return StreamingResponse(frames(), media_type=SSE_MEDIA_TYPE, headers=SSE_HEADERS)
