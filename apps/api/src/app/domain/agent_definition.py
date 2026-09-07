"""Ephemeral agent workshop definition (no LLM I/O)."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.errors import MessageValidationError


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    system_prompt: str
    preferred_model: str
    temperature: float | None = None
    max_tokens: int | None = None


def validate_agent_run(
    definition: AgentDefinition,
    *,
    message: str,
    max_message_chars: int,
) -> None:
    """Raise MessageValidationError if definition or user message is unusable."""
    system = (definition.system_prompt or "").strip()
    user = (message or "").strip()
    if not system:
        raise MessageValidationError("Инструкция агента не должна быть пустой.")
    if not user:
        raise MessageValidationError("Сообщение не должно быть пустым.")
    if len(system) > max_message_chars:
        raise MessageValidationError(
            f"Инструкция агента длиннее лимита в {max_message_chars} символов."
        )
    if len(user) > max_message_chars:
        raise MessageValidationError(f"Сообщение длиннее лимита в {max_message_chars} символов.")
    name = (definition.name or "").strip()
    if len(name) > 120:
        raise MessageValidationError("Имя агента слишком длинное.")
