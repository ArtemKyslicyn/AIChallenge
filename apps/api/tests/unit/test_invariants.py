"""Unit tests for Day-14 dialog invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.agent_run import run_agent_with_dialog
from app.application.invariants_ops import apply_invariant_events_to_dialog
from app.domain.agent_definition import AgentDefinition
from app.domain.agent_dialog import AgentDialog
from app.domain.entities import ChatMessage, CompletionResult
from app.domain.errors import MessageValidationError
from app.domain.generation import GenerationParams
from app.domain.invariants import (
    KINDS,
    Invariant,
    InvariantEvent,
    apply_invariant_event,
    build_refusal_reply,
    default_invariants,
    dump_invariants,
    find_invariant_conflicts,
    format_invariants_block,
    normalize_kind,
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


def test_parse_drops_invalid_and_duplicate_rows() -> None:
    raw = [
        {"id": "ok", "kind": "stack", "statement": "Postgres", "triggers": ["mongo"]},
        {"id": "ok", "kind": "stack", "statement": "duplicate id ignored"},
        {"kind": "stack", "statement": "no id"},
        {"id": "empty", "kind": "stack", "statement": "   "},
        {"id": "bad-kind", "kind": "frontend", "statement": "Vue"},
        "not-a-dict",
        {"id": "dead", "kind": "business", "statement": "off", "active": False},
    ]
    items = parse_invariants(raw)
    assert [i.id for i in items] == ["ok", "dead"]
    assert items[0].triggers == ["mongo"]
    assert items[1].active is False
    assert parse_invariants(None) == []
    assert parse_invariants({"not": "list"}) == []


def test_dump_roundtrip_keeps_triggers_and_kinds() -> None:
    seeded = default_invariants()
    assert {i.kind for i in seeded} == set(KINDS)
    dumped = dump_invariants(seeded)
    assert all("triggers" in row for row in dumped)
    assert [i.kind for i in parse_invariants(dumped)] == list(KINDS)


@pytest.mark.parametrize(
    ("alias", "kind"),
    [
        ("архитектура", "architecture"),
        ("arch", "architecture"),
        ("стек", "stack"),
        ("решение", "decision"),
        ("decision", "decision"),
        ("правило", "business"),
        ("бизнес", "business"),
        ("rule", "business"),
    ],
)
def test_normalize_kind_aliases(alias: str, kind: str) -> None:
    assert normalize_kind(alias) == kind


def test_normalize_kind_rejects_unknown() -> None:
    with pytest.raises(MessageValidationError, match="kind"):
        normalize_kind("frontend")


def test_add_requires_statement_and_known_kind() -> None:
    with pytest.raises(MessageValidationError, match="statement"):
        apply_invariant_event([], InvariantEvent(name="add", kind="stack", statement="  "))
    with pytest.raises(MessageValidationError, match="kind"):
        apply_invariant_event([], InvariantEvent(name="add", kind="vue", statement="SPA"))
    with pytest.raises(MessageValidationError, match="event"):
        apply_invariant_event([], InvariantEvent(name="merge"))


def test_add_truncates_statement_and_replaces_same_id() -> None:
    long = "x" * 600
    items, _ = apply_invariant_event(
        [],
        InvariantEvent(name="add", kind="stack", statement=long, invariant_id="same"),
    )
    assert len(items[0].statement) == 500
    items, label = apply_invariant_event(
        items,
        InvariantEvent(
            name="add",
            kind="architecture",
            statement="слои",
            invariant_id="same",
        ),
    )
    assert len(items) == 1
    assert items[0].kind == "architecture"
    assert "добавлен" in label


def test_update_and_reset_and_seed_replace() -> None:
    custom, _ = apply_invariant_event(
        [],
        InvariantEvent(name="add", kind="stack", statement="Kafka"),
    )
    with pytest.raises(MessageValidationError, match="invariant_id"):
        apply_invariant_event(custom, InvariantEvent(name="update", kind="stack", statement="x"))
    with pytest.raises(MessageValidationError, match="не найден"):
        apply_invariant_event(
            custom,
            InvariantEvent(
                name="update",
                kind="stack",
                statement="x",
                invariant_id="missing",
            ),
        )
    emptied, label = apply_invariant_event(custom, InvariantEvent(name="reset"))
    assert emptied == []
    assert "сброшены" in label
    seeded, _ = apply_invariant_event(custom, InvariantEvent(name="seed"))
    assert [i.kind for i in seeded] == list(KINDS)


def test_remove_requires_existing_id() -> None:
    with pytest.raises(MessageValidationError, match="обязателен"):
        apply_invariant_event([], InvariantEvent(name="remove"))


@pytest.mark.parametrize(
    ("message", "expected_kinds"),
    [
        ("Переведи API на Django без слоёв", {"architecture", "stack"}),
            ("разнеси по микросервисам", {"architecture"}),
            ("разнести по микросервисам", {"architecture"}),
            ("выкинь hexagonal", {"architecture"}),
        ("mongodb вместо postgres", {"stack"}),
        ("убери model_id с ответов", {"decision"}),
        ("назови роли patient и doctor в коде", {"business"}),
        ("переведи API на rails и laravel", {"stack"}),
        ("давай split into microservices", {"architecture"}),
        ("предлагаю hide model_id", {"decision"}),
        ("сделай роль doctor в API", {"business"}),
    ],
)
def test_default_conflicts_cover_every_kind(message: str, expected_kinds: set[str]) -> None:
    kinds = {c.invariant.kind for c in find_invariant_conflicts(default_invariants(), message)}
    assert expected_kinds <= kinds


@pytest.mark.parametrize(
    "message",
    [
        "Как устроен Django в учебнике?",
        "Что такое микросервис в теории?",
        "patient в медицине — это термин",
        "как показать model_id в UI, не ломая слои?",
        "",
        "   ",
    ],
)
def test_mentions_without_proposal_do_not_use_weak_heuristics(message: str) -> None:
    assert find_invariant_conflicts(default_invariants(), message) == []


def test_challenge_violation_hits_architecture_and_stack() -> None:
    msg = "Переведи API на Django без слоёв и разнеси по микросервисам"
    kinds = {c.invariant.kind for c in find_invariant_conflicts(default_invariants(), msg)}
    assert {"architecture", "stack"} <= kinds


def test_strong_phrase_refuses_without_proposal_marker() -> None:
    kinds = {
        c.invariant.kind
        for c in find_invariant_conflicts(default_invariants(), "просто без слоёв в коде")
    }
    assert "architecture" in kinds


def test_custom_trigger_is_case_insensitive_and_inactive_skipped() -> None:
    active = Invariant(
        id="k",
        kind="stack",
        statement="Kafka only",
        triggers=["RabbitMQ"],
    )
    dead = Invariant(
        id="d",
        kind="stack",
        statement="Kafka only",
        active=False,
        triggers=["RabbitMQ"],
    )
    hits = find_invariant_conflicts([active], "нужен rabbitmq сегодня")
    assert hits[0].matched.lower() == "rabbitmq"
    assert find_invariant_conflicts([dead], "нужен rabbitmq сегодня") == []


def test_format_block_empty_and_lists_triggers() -> None:
    assert format_invariants_block([]) == ""
    inv = Invariant(
        id="k",
        kind="stack",
        statement="Kafka",
        triggers=["rabbitmq"],
    )
    block = format_invariants_block([inv])
    assert "триггеры: rabbitmq" in block
    assert "стек" in block
    off = Invariant(id="x", kind="stack", statement="Kafka", active=False, triggers=["x"])
    assert format_invariants_block([off]) == ""


def test_refusal_cites_statement_match_and_truncates() -> None:
    assert build_refusal_reply([], "x") == ""
    items = default_invariants()
    conflicts = find_invariant_conflicts(items, "Переведи API на Django без слоёв")
    text = build_refusal_reply(conflicts, "я" * 300)
    assert "…" in text
    assert "совпадение:" in text
    assert "Модульный монолит" in text
    assert "FastAPI" in text


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("посеять инварианты", "seed"),
        ("примеры инвариантов", "seed"),
        ("инварианты: seed", "seed"),
        ("/инварианты seed", "seed"),
        ("очистить инварианты", "reset"),
        ("сбросить инварианты", "reset"),
        ("инварианты: сброс", "reset"),
        ("/инварианты reset", "reset"),
    ],
)
def test_chat_seed_and_reset_aliases(text: str, name: str) -> None:
    ev = parse_invariant_chat_command(text)
    assert ev is not None and ev.name == name


@pytest.mark.parametrize(
    "text",
    [
        "как добавить инвариант в API?",
        "Инварианты в математике — это свойства",
        "стек у нас FastAPI",
        "/help",
    ],
)
def test_ordinary_chat_is_not_an_invariant_command(text: str) -> None:
    assert parse_invariant_chat_commands(text) == []


def test_chat_block_covers_all_four_kinds_then_applies() -> None:
    block = "\n".join(
        [
            "инварианты:",
            "архитектура: монолит | микросервисы",
            "стек: FastAPI | django",
            "решение: model_id на каждом ответе | без model_id",
            "правило: нейтральные имена | patient",
        ]
    )
    events = parse_invariant_chat_commands(block)
    assert [e.kind for e in events] == list(KINDS)
    items: list[Invariant] = []
    for ev in events:
        items, _ = apply_invariant_event(items, ev)
    assert {i.kind for i in items} == set(KINDS)
    kinds = {c.invariant.kind for c in find_invariant_conflicts(items, "переведи на django")}
    assert "stack" in kinds


def test_slash_and_english_chat_add() -> None:
    ev = parse_invariant_chat_command("/инвариант decision: expose model_id | hide model_id")
    assert ev is not None and ev.kind == "decision"
    assert ev.triggers == ["hide model_id"]
    ev2 = parse_invariant_chat_command("invariant stack: only FastAPI | rails")
    assert ev2 is not None and ev2.kind == "stack"


def test_chat_remove_and_empty_statement_skipped() -> None:
    ev = parse_invariant_chat_command("удалить инвариант: stack-fastapi-react-pg")
    assert ev is not None and ev.name == "remove"
    assert ev.invariant_id == "stack-fastapi-react-pg"
    assert parse_invariant_chat_commands("инвариант стек:") == []


def _dialog(
    *,
    draft: str = "draft-inv",
    invariants: list[dict[str, object]] | None = None,
) -> AgentDialog:
    return AgentDialog(
        id=uuid4(),
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id=draft,
        name="Inv",
        system_prompt="Be brief.",
        preferred_model="auto",
        temperature=0.2,
        max_tokens=80,
        messages=[],
        invariants=invariants
        if invariants is not None
        else [i.to_dict() for i in default_invariants()],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


async def _run(
    message: str, dialog: AgentDialog | None = None
) -> tuple[object, AgentDialog, _FakeRouter]:
    dialog = dialog or _dialog()
    repo = _MemRepo(dialog)
    router = _FakeRouter()
    outcome, saved = await run_agent_with_dialog(
        definition=AgentDefinition(
            name="Inv", system_prompt="Be brief.", preferred_model="auto", max_tokens=80
        ),
        message=message,
        router=router,  # type: ignore[arg-type]
        dialogs=repo,  # type: ignore[arg-type]
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id=dialog.client_draft_id,
        enabled=True,
        max_message_chars=8000,
    )
    return outcome, saved, router


@pytest.mark.parametrize(
    ("message", "kind"),
    [
        ("разнеси по микросервисам", "architecture"),
        ("mongodb вместо postgres", "stack"),
        ("убери model_id", "decision"),
        ("врач и пациент в коде", "business"),
    ],
)
@pytest.mark.asyncio
async def test_run_refuses_each_kind_without_llm(message: str, kind: str) -> None:
    outcome, saved, router = await _run(message)
    assert router.calls == 0
    assert outcome.invariant_conflict is True
    assert outcome.result.model_id == "invariants"
    assert saved.messages[-1].model_id == "invariants"
    assert saved.messages[-2].role == "user"
    hit = {c.invariant.kind for c in find_invariant_conflicts(default_invariants(), message)}
    assert kind in hit
    assert parse_invariants(saved.invariants)
    assert "ОТКАЗ" in outcome.result.content
    assert "совпадение" in outcome.result.content


@pytest.mark.asyncio
async def test_run_refuses_custom_trigger_without_llm() -> None:
    inv = Invariant(
        id="queue",
        kind="stack",
        statement="Очереди только Kafka",
        triggers=["rabbitmq"],
    )
    outcome, saved, router = await _run(
        "подключи RabbitMQ",
        _dialog(invariants=[inv.to_dict()]),
    )
    assert router.calls == 0
    assert outcome.invariant_conflict is True
    assert "Kafka" in outcome.result.content
    assert saved.invariants[0]["id"] == "queue"


@pytest.mark.asyncio
async def test_run_without_invariants_does_not_inject_block() -> None:
    outcome, saved, router = await _run(
        "Как добавить эндпоинт в adapters?",
        _dialog(invariants=[]),
    )
    assert router.calls == 1
    assert outcome.invariant_conflict is False
    assert "[инварианты · отдельно от диалога" not in router.last_messages[0].content
    assert saved.messages[-1].model_id == "fake-model"


@pytest.mark.asyncio
async def test_ops_applies_chat_block_onto_dialog_column() -> None:
    dialog = _dialog(invariants=[])
    repo = _MemRepo(dialog)
    events = parse_invariant_chat_commands(
        "инварианты:\n"
        "архитектура: монолит\n"
        "стек: FastAPI\n"
        "решение: model_id\n"
        "правило: нейтральные имена"
    )
    saved, label = await apply_invariant_events_to_dialog(dialog, events, dialogs=repo)
    assert "добавлен" in label
    assert {i.kind for i in parse_invariants(saved.invariants)} == set(KINDS)
    assert saved.invariants != saved.messages
