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
    assert result.result.content == "ok-answer"
    assert result.result.model_id == "fake-model"
    assert result.tokens.completion >= 1
    assert result.tokens.truncation.applied is False
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


@pytest.mark.asyncio
async def test_run_agent_truncates_history_under_low_context_limit() -> None:
    from datetime import UTC, datetime

    from app.domain.agent_dialog import AgentDialogMessage

    router = _FakeRouter()
    blob = "z" * 400
    prior = [
        AgentDialogMessage(
            id="1", role="user", content=blob, created_at=datetime.now(UTC)
        ),
        AgentDialogMessage(
            id="2",
            role="assistant",
            content=blob,
            created_at=datetime.now(UTC),
            model_id="fake",
        ),
        AgentDialogMessage(
            id="3", role="user", content="short", created_at=datetime.now(UTC)
        ),
        AgentDialogMessage(
            id="4",
            role="assistant",
            content="ok",
            created_at=datetime.now(UTC),
            model_id="fake",
        ),
    ]
    outcome = await run_agent(
        definition=AgentDefinition(
            name="N", system_prompt="S", preferred_model="auto", max_tokens=32
        ),
        message="NOW",
        router=router,  # type: ignore[arg-type]
        enabled=True,
        max_message_chars=8000,
        history=prior,
        context_limit=96,
    )
    assert outcome.tokens.truncation.applied is True
    assert outcome.tokens.history_before > outcome.tokens.history_after
    joined = " ".join(m.content for m in router.last_messages)
    assert blob not in joined or outcome.tokens.truncation.dropped_messages >= 1
    assert router.last_messages[-1].content == "NOW"


@pytest.mark.asyncio
async def test_compress_refreshes_summary_and_shrinks_prompt() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.application.agent_run import run_agent_with_dialog
    from app.domain.agent_dialog import AgentDialog, AgentDialogMessage

    class _MemRepo:
        def __init__(self) -> None:
            self.dialog: AgentDialog | None = None

        async def get(self, dialog_id):  # noqa: ANN001
            return self.dialog if self.dialog and self.dialog.id == dialog_id else None

        async def get_by_client_draft(self, *, client_visitor_id, client_draft_id):  # noqa: ANN001
            if (
                self.dialog
                and self.dialog.client_visitor_id == client_visitor_id
                and self.dialog.client_draft_id == client_draft_id
            ):
                return self.dialog
            return None

        async def save(self, dialog: AgentDialog) -> AgentDialog:
            self.dialog = dialog
            return dialog

    fat = "факт " * 30
    msgs = []
    for i in range(12):
        msgs.append(
            AgentDialogMessage(
                id=str(i * 2),
                role="user",
                content=f"U{i} {fat}",
                created_at=datetime.now(UTC),
            )
        )
        msgs.append(
            AgentDialogMessage(
                id=str(i * 2 + 1),
                role="assistant",
                content=f"A{i} {fat}",
                created_at=datetime.now(UTC),
                model_id="fake",
            )
        )
    repo = _MemRepo()
    repo.dialog = AgentDialog(
        id=uuid4(),
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id="draft-c",
        name="C",
        system_prompt="Be brief.",
        preferred_model="auto",
        temperature=0.2,
        max_tokens=100,
        messages=msgs,
        summary_text="",
        summary_until_count=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    router = _FakeRouter()
    outcome, saved = await run_agent_with_dialog(
        definition=AgentDefinition(
            name="C", system_prompt="Be brief.", preferred_model="auto", max_tokens=100
        ),
        message="Что помнишь?",
        router=router,  # type: ignore[arg-type]
        dialogs=repo,  # type: ignore[arg-type]
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id="draft-c",
        enabled=True,
        max_message_chars=8000,
        compress=True,
        recent_keep=4,
        summarize_every=8,
    )
    assert outcome.compression is not None
    assert outcome.compression.enabled is True
    assert outcome.compression.summary_refreshed is True
    assert outcome.compression.tokens_compressed_est < outcome.compression.tokens_raw_est
    assert saved.summary_text
    assert saved.summary_until_count > 0
    # Main call should include summary in system and only recent turns
    assert any("Сводка" in m.content for m in router.last_messages if m.role.value == "system")
