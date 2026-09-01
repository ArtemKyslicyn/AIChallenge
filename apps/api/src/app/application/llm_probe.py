"""Direct LLM probe: same provider and router as chat; nothing is persisted."""

from __future__ import annotations

from app.domain.entities import AUTO_MODEL, ChatMessage, CompletionResult
from app.domain.errors import ProbeDisabledError
from app.domain.generation import GenerationParams, apply_generation_to_messages
from app.domain.ports import ChatRouter


async def complete_probe(
    *,
    router: ChatRouter,
    messages: list[ChatMessage],
    preferred_model: str = AUTO_MODEL,
    enabled: bool,
    generation: GenerationParams | None = None,
) -> CompletionResult:
    if not enabled:
        raise ProbeDisabledError("Probe к модели отключён конфигурацией.")
    prepared = apply_generation_to_messages(messages, generation)
    return await router.complete_chat(
        prepared, preferred_model=preferred_model, generation=generation
    )
