"""Direct LLM probe: same provider and router as chat, but no persistence."""

from __future__ import annotations

from app.domain.entities import AUTO_MODEL, ChatMessage, CompletionResult
from app.domain.errors import ProbeDisabledError
from app.domain.ports import ChatRouter


async def complete_probe(
    *,
    router: ChatRouter,
    messages: list[ChatMessage],
    preferred_model: str = AUTO_MODEL,
    enabled: bool,
) -> CompletionResult:
    if not enabled:
        raise ProbeDisabledError("Probe к модели отключён конфигурацией.")
    return await router.complete_chat(messages, preferred_model=preferred_model)
