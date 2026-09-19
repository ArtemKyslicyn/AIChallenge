"""Unit tests for Day-14 dialog invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.agent_run import run_agent_with_dialog
from app.domain.agent_definition import AgentDefinition
from app.domain.agent_dialog import AgentDialog
from app.domain.entities import ChatMessage, CompletionResult
from app.domain.errors import MessageValidationError
from app.domain.generation import GenerationParams
from app.domain.invariants import (
    Invariant,
    InvariantEvent,
    apply_invariant_event,
    build_refusal_reply,
    default_invariants,
    find_invariant_conflicts,
    format_invariants_block,
    normalize_triggers,
    parse_invariant_chat_command,
    parse_invariant_chat_commands,
    parse_invariants,
)


@dataclass
class _FakeRouter:
    last_messages: list[ChatMessage] = field(default_factory=list)
    calls: int = 0

    async def complete_chat(
        self,
        messages: list[ChatMessage],
        preferred_model: str = "auto",
        *,
        generation: GenerationParams | None = None,
        tools: object = None,
    ) -> CompletionResult:
        self.calls += 1
        self.last_messages = list(messages)
        return CompletionResult(content="ok-answer инварианты: ок", model_id="fake-model")


class _MemRepo:
    def __init__(self, dialog: AgentDialog) -> None:
        self.dialog = dialog

    async def get(self, dialog_id):  # noqa: ANN001
        return self.dialog if self.dialog.id == dialog_id else None

    async def get_by_client_draft(self, *, client_visitor_id, client_draft_id):  # noqa: ANN001
        if (
            self.dialog.client_visitor_id == client_visitor_id
            and self.dialog.client_draft_id == client_draft_id
        ):
            return self.dialog
        return None

    async def save(self, dialog: AgentDialog) -> AgentDialog:
        self.dialog = dialog
        return dialog


def test_seed_and_parse_roundtrip() -> None:
    seeded, label = apply_invariant_event([], InvariantEvent(name="seed"))
    assert "4" in label
    assert len(seeded) == 4
    restored = parse_invariants([i.to_dict() for i in seeded])
    assert [i.id for i in restored] == [i.id for i in seeded]


def test_add_remove() -> None:
    items, _ = apply_invariant_event(
        [],
        InvariantEvent(name="add", kind="стек", statement="Только Postgres"),
    )
    assert items[0].kind == "stack"
    items, _ = apply_invariant_event(items, InvariantEvent(name="remove", invariant_id=items[0].id))
    assert items == []
    with pytest.raises(MessageValidationError):
        apply_invariant_event([], InvariantEvent(name="remove", invariant_id="missing"))


def test_custom_triggers_roundtrip_and_update() -> None:
    items, _ = apply_invariant_event(
        [],
        InvariantEvent(
            name="add",
            kind="stack",
            statement="Очереди только через Kafka",
            triggers=["rabbitmq", "redis streams"],
        ),
    )
    assert items[0].triggers == ["rabbitmq", "redis streams"]
    restored = parse_invariants([items[0].to_dict()])
    assert restored[0].triggers == ["rabbitmq", "redis streams"]
    items, label = apply_invariant_event(
        items,
        InvariantEvent(
            name="update",
            kind="stack",
            statement="Очереди: Kafka, не Rabbit",
            invariant_id=items[0].id,
            triggers=["rabbit"],
        ),
    )
    assert "сохранён" in label
    assert items[0].statement.startswith("Очереди: Kafka")
    assert items[0].triggers == ["rabbit"]


def test_custom_trigger_conflicts_without_kind_heuristic() -> None:
    inv = Invariant(
        id="queue-kafka",
        kind="stack",
        statement="Очереди только через Kafka",
        triggers=["rabbitmq"],
    )
    conflicts = find_invariant_conflicts([inv], "подключи RabbitMQ для задач")
    assert len(conflicts) == 1
    assert conflicts[0].matched.lower() == "rabbitmq"
    assert find_invariant_conflicts([inv], "как устроен consumer в Kafka?") == []


def test_normalize_triggers_dedupes_and_caps() -> None:
    assert normalize_triggers("Django, django; rails\n, x") == ["Django", "rails"]
    assert len(normalize_triggers([f"ph{i:02d}" for i in range(20)])) == 12


def test_conflict_django_without_layers() -> None:
    items = default_invariants()
    msg = "Переведи API на Django без слоёв"
    conflicts = find_invariant_conflicts(items, msg)
    kinds = {c.invariant.kind for c in conflicts}
    assert "architecture" in kinds
    assert "stack" in kinds
    text = build_refusal_reply(conflicts, msg)
    assert "ОТКАЗ" in text
    assert "архитектура" in text
    assert "стек" in text
    assert "Обход не предлагаю" in text


def test_compliant_request_has_no_conflict() -> None:
    items = default_invariants()
    msg = "Как добавить эндпоинт списка инвариантов в apps/api adapters, не ломая слои?"
    assert find_invariant_conflicts(items, msg) == []


def test_inactive_invariant_is_ignored() -> None:
    inv = Invariant(
        id="x",
        kind="stack",
        statement="Только FastAPI",
        active=False,
    )
    assert find_invariant_conflicts([inv], "переведи API на Django") == []


def test_format_block_separate_from_dialog() -> None:
    block = format_invariants_block(default_invariants())
    assert "[инварианты · отдельно от диалога" in block
    assert "архитектура" in block
    assert "не предлагай обход" in block.lower() or "не предлагай обход" in block


def test_parse_chat_commands() -> None:
    ev = parse_invariant_chat_command("инвариант стек: только Postgres | django, rails")
    assert ev is not None and ev.name == "add" and ev.kind == "stack"
    assert ev.triggers == ["django", "rails"]
    assert parse_invariant_chat_command("посеять инварианты").name == "seed"  # type: ignore[union-attr]
    assert parse_invariant_chat_command("примеры инвариантов").name == "seed"  # type: ignore[union-attr]
    assert parse_invariant_chat_command("очистить инварианты").name == "reset"  # type: ignore[union-attr]
    assert parse_invariant_chat_command("снять инвариант: arch-hexagonal").invariant_id == (
        "arch-hexagonal"
    )
    assert parse_invariant_chat_command("привет") is None
    assert parse_invariant_chat_command("Инварианты в математике — это свойства") is None


def test_parse_chat_block_from_message() -> None:
    block = "\n".join(
        [
            "инварианты:",
            "стек: очереди только Kafka | rabbitmq",
            "правило: нейтральные имена, без чужого домена",
            "инвариант архитектура Модульный монолит, не микросервисы",
        ]
    )
    events = parse_invariant_chat_commands(block)
    assert [e.kind for e in events] == ["stack", "business", "architecture"]
    assert events[0].triggers == ["rabbitmq"]
    naked = parse_invariant_chat_command("добавь инвариант: только свой контур | чужой api")
    assert naked is not None and naked.kind == "business"
    assert naked.triggers == ["чужой api"]


def test_chat_covers_every_kind_and_alias() -> None:
    samples = {
        "architecture": (
            "инвариант архитектура: слои domain → adapters | микросервисы",
            "инвариант arch: hexagonal only",
            "invariant architecture: keep the modular monolith",
        ),
        "stack": (
            "инвариант стек: FastAPI + Postgres | django",
            "инвариант stack: only FastAPI",
        ),
        "decision": (
            "инвариант решение: каждый ответ с model_id | без model_id",
            "инвариант decision: expose model_id",
            "зафиксируй инвариант решение Каждый ответ атрибутирует model_id",
        ),
        "business": (
            "инвариант правило: нейтральные имена | patient",
            "инвариант бизнес: без чужого домена",
            "инвариант rule: domain-agnostic names",
        ),
    }
    for kind, lines in samples.items():
        for line in lines:
            ev = parse_invariant_chat_command(line)
            assert ev is not None, line
            assert ev.name == "add" and ev.kind == kind, (line, ev)


def _dialog_with_defaults() -> AgentDialog:
    return AgentDialog(
        id=uuid4(),
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id="draft-inv",
        name="Inv",
        system_prompt="Be brief.",
        preferred_model="auto",
        temperature=0.2,
        max_tokens=80,
        messages=[],
        invariants=[i.to_dict() for i in default_invariants()],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_run_refuses_without_calling_llm() -> None:
    repo = _MemRepo(_dialog_with_defaults())
    router = _FakeRouter()
    outcome, saved = await run_agent_with_dialog(
        definition=AgentDefinition(
            name="Inv", system_prompt="Be brief.", preferred_model="auto", max_tokens=80
        ),
        message="Переведи API на Django без слоёв и разнеси по микросервисам",
        router=router,  # type: ignore[arg-type]
        dialogs=repo,  # type: ignore[arg-type]
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id="draft-inv",
        enabled=True,
        max_message_chars=8000,
    )
    assert router.calls == 0
    assert outcome.invariant_conflict is True
    assert outcome.result.model_id == "invariants"
    assert "ОТКАЗ" in outcome.result.content
    assert "hexagonal" in outcome.result.content.lower() or "слои" in outcome.result.content
    assert saved.messages[-1].role == "assistant"
    assert saved.messages[-1].model_id == "invariants"
    assert saved.invariants  # still stored apart from turns


@pytest.mark.asyncio
async def test_run_injects_invariants_block_when_compliant() -> None:
    repo = _MemRepo(_dialog_with_defaults())
    router = _FakeRouter()
    outcome, _saved = await run_agent_with_dialog(
        definition=AgentDefinition(
            name="Inv", system_prompt="Be brief.", preferred_model="auto", max_tokens=80
        ),
        message="Как добавить эндпоинт в apps/api adapters, не ломая слои?",
        router=router,  # type: ignore[arg-type]
        dialogs=repo,  # type: ignore[arg-type]
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id="draft-inv",
        enabled=True,
        max_message_chars=8000,
    )
    assert router.calls == 1
    assert outcome.invariant_conflict is False
    system = router.last_messages[0].content
    assert "[инварианты · отдельно от диалога" in system
    assert "FastAPI" in system
    assert outcome.result.model_id == "fake-model"
