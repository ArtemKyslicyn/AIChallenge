from app.domain.generation import (
    FORMAT_BLOCK,
    LENGTH_BLOCK,
    GenerationParams,
    PromptControlFlags,
    apply_generation_to_messages,
    apply_prompt_controls_to_text,
)
from app.domain.entities import ChatMessage, MessageRole


def test_apply_prompt_controls_appends_blocks() -> None:
    text = apply_prompt_controls_to_text(
        "REST API",
        PromptControlFlags(format=True, length=True, stop=True),
    )
    assert text.startswith("REST API")
    assert FORMAT_BLOCK in text
    assert LENGTH_BLOCK in text
    assert "END" in text


def test_generation_resolves_length_max_tokens() -> None:
    params = GenerationParams(prompt_controls=PromptControlFlags(length=True))
    assert params.resolved_max_tokens() == 80


def test_apply_generation_to_last_user_turn() -> None:
    turns = [
        ChatMessage(role=MessageRole.SYSTEM, content="sys"),
        ChatMessage(role=MessageRole.USER, content="hello"),
    ]
    out = apply_generation_to_messages(
        turns,
        GenerationParams(prompt_controls=PromptControlFlags(format=True)),
    )
    assert out[1].content.startswith("hello")
    assert FORMAT_BLOCK in out[1].content
