"""Unit tests for run_agent use case."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.application.agent_run import run_agent
from app.domain.agent_definition import AgentDefinition
from app.domain.entities import ChatMessage, CompletionResult
from app.domain.errors import AgentsRunDisabledError
from app.domain.generation import GenerationParams


@dataclass
class _FakeRouter:
    last_messages: list[ChatMessage] = field(default_factory=list)
    last_model: str | None = None
    last_generation: GenerationParams | None = None

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = "auto",
        *,
        generation: GenerationParams | None = None,
        tools: object = None,
    ) -> CompletionResult:
        self.last_messages = list(messages)
        self.last_model = preferred_model
        self.last_generation = generation
        return CompletionResult(content="ok-answer", model_id="fake-model")

    async def stream_chat(self, *args: object, **kwargs: object):  # pragma: no cover
        raise NotImplementedError


@pytest.mark.asyncio
async def test_run_agent_assembles_system_and_user() -> None:
    router = _FakeRouter()
    definition = AgentDefinition(
        name="N",
        system_prompt="Be brief.",
        preferred_model="model-a",
        temperature=0.2,
        max_tokens=100,
    )
    gen = GenerationParams(temperature=0.2, max_tokens=100)
    result = await run_agent(
        definition=definition,
        message="Hello",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        generation=gen,
    )
    assert result.content == "ok-answer"
    assert result.model_id == "fake-model"
    assert [m.role.value for m in router.last_messages] == ["system", "user"]
    assert router.last_messages[0].content == "Be brief."
    assert router.last_messages[1].content == "Hello"
    assert router.last_model == "model-a"
    assert router.last_generation is gen


@pytest.mark.asyncio
async def test_run_agent_includes_history() -> None:
    from app.domain.agent_dialog import AgentDialogMessage
    from datetime import UTC, datetime

    router = _FakeRouter()
    definition = AgentDefinition(
        name="N", system_prompt="Remember.", preferred_model="auto"
    )
    prior = [
        AgentDialogMessage(
            id="1",
            role="user",
            content="Меня зовут Влад",
            created_at=datetime.now(UTC),
        ),
        AgentDialogMessage(
            id="2",
            role="assistant",
            content="Приятно познакомиться, Влад.",
            created_at=datetime.now(UTC),
            model_id="fake",
        ),
    ]
    await run_agent(
        definition=definition,
        message="Как меня зовут?",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        history=prior,
    )
    roles = [m.role.value for m in router.last_messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert router.last_messages[1].content == "Меня зовут Влад"
    assert router.last_messages[3].content == "Как меня зовут?"

    with pytest.raises(AgentsRunDisabledError):
        await run_agent(
            definition=AgentDefinition(
                name="N", system_prompt="S", preferred_model="auto"
            ),
            message="Hi",
            router=_FakeRouter(),  # type: ignore[arg-type]
            enabled=False,
            max_message_chars=8000,
        )
