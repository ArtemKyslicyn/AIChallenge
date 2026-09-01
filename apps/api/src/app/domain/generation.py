"""Generation knobs for LLM calls (probe and, later, chat).

Prompt-control text mirrors the web ``promptControls.ts`` blocks so UI and API
stay aligned without a shared runtime bundle.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.entities import ChatMessage, MessageRole

PROMPT_SEPARATOR = "\n\n— Как отвечать —\n"

FORMAT_BLOCK = (
    "Формат ответа: ровно 3 пункта, каждый с новой строки, "
    "с префиксами «1. », «2. », «3. ». Без вступления и без текста вне пунктов."
)
LENGTH_BLOCK = "Ограничение длины: не больше 50 слов во всём ответе."
STOP_BLOCK = (
    "Условие завершения: после основного ответа напиши отдельной строкой "
    "ровно END и больше ничего не добавляй."
)

#: Rough token budget when only the «кратко» prompt control is on.
LENGTH_CONTROL_MAX_TOKENS = 80


@dataclass(slots=True, frozen=True)
class PromptControlFlags:
    format: bool = False
    length: bool = False
    stop: bool = False

    def any_enabled(self) -> bool:
        return self.format or self.length or self.stop


@dataclass(slots=True, frozen=True)
class GenerationParams:
    temperature: float | None = None
    max_tokens: int | None = None
    stop: tuple[str, ...] | None = None
    prompt_controls: PromptControlFlags | None = None
    reasoning: bool = False

    def resolved_max_tokens(self) -> int | None:
        if self.max_tokens is not None:
            return self.max_tokens
        controls = self.prompt_controls
        if controls and controls.length:
            return LENGTH_CONTROL_MAX_TOKENS
        return None


def apply_prompt_controls_to_text(user_text: str, controls: PromptControlFlags) -> str:
    trimmed = user_text.strip()
    if not trimmed or not controls.any_enabled():
        return trimmed
    parts: list[str] = []
    if controls.format:
        parts.append(FORMAT_BLOCK)
    if controls.length:
        parts.append(LENGTH_BLOCK)
    if controls.stop:
        parts.append(STOP_BLOCK)
    return f"{trimmed}{PROMPT_SEPARATOR}{'\n'.join(parts)}"


def apply_generation_to_messages(
    messages: list[ChatMessage], generation: GenerationParams | None
) -> list[ChatMessage]:
    if not generation:
        return messages
    controls = generation.prompt_controls
    if not controls or not controls.any_enabled():
        return messages
    out = list(messages)
    for index in range(len(out) - 1, -1, -1):
        if out[index].role == MessageRole.USER:
            out[index] = ChatMessage(
                role=out[index].role,
                content=apply_prompt_controls_to_text(out[index].content, controls),
            )
            return out
    return out
