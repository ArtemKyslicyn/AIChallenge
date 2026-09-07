"""Run one ephemeral agent definition against the chat router."""

from __future__ import annotations

from app.domain.agent_definition import AgentDefinition, validate_agent_run
from app.domain.entities import AUTO_MODEL, ChatMessage, CompletionResult, MessageRole
from app.domain.errors import AgentsRunDisabledError
from app.domain.generation import GenerationParams
from app.domain.ports import ChatRouter


async def run_agent(
    *,
    definition: AgentDefinition,
    message: str,
    router: ChatRouter,
    enabled: bool,
    max_message_chars: int,
    generation: GenerationParams | None = None,
) -> CompletionResult:
    if not enabled:
        raise AgentsRunDisabledError("Запуск агентов отключён конфигурацией.")
    validate_agent_run(definition, message=message, max_message_chars=max_message_chars)
    turns = [
        ChatMessage(role=MessageRole.SYSTEM, content=definition.system_prompt.strip()),
        ChatMessage(role=MessageRole.USER, content=message.strip()),
    ]
    preferred = (definition.preferred_model or AUTO_MODEL).strip() or AUTO_MODEL
    return await router.complete_chat(
        turns, preferred_model=preferred, generation=generation
    )
