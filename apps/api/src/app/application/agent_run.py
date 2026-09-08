"""Run agent with optional prior turns; persist dialog turns in Postgres."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.agent_definition import AgentDefinition, validate_agent_run
from app.domain.agent_dialog import AgentDialog, AgentDialogMessage
from app.domain.entities import AUTO_MODEL, ChatMessage, CompletionResult, MessageRole
from app.domain.errors import AgentsRunDisabledError, MessageValidationError
from app.domain.generation import GenerationParams
from app.domain.ports import AgentDialogRepository, ChatRouter

#: Soft cap so context / JSONB stay bounded.
MAX_STORED_MESSAGES = 40


async def run_agent(
    *,
    definition: AgentDefinition,
    message: str,
    router: ChatRouter,
    enabled: bool,
    max_message_chars: int,
    generation: GenerationParams | None = None,
    history: list[AgentDialogMessage] | None = None,
) -> CompletionResult:
    if not enabled:
        raise AgentsRunDisabledError("Запуск агентов отключён конфигурацией.")
    validate_agent_run(definition, message=message, max_message_chars=max_message_chars)

    turns: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=definition.system_prompt.strip()),
    ]
    for prior in history or []:
        if prior.role == "user":
            turns.append(ChatMessage(role=MessageRole.USER, content=prior.content))
        elif prior.role == "assistant":
            turns.append(ChatMessage(role=MessageRole.ASSISTANT, content=prior.content))
    turns.append(ChatMessage(role=MessageRole.USER, content=message.strip()))

    preferred = (definition.preferred_model or AUTO_MODEL).strip() or AUTO_MODEL
    return await router.complete_chat(
        turns, preferred_model=preferred, generation=generation
    )


async def run_agent_with_dialog(
    *,
    definition: AgentDefinition,
    message: str,
    router: ChatRouter,
    dialogs: AgentDialogRepository,
    client_visitor_id: str,
    client_draft_id: str,
    enabled: bool,
    max_message_chars: int,
    generation: GenerationParams | None = None,
    dialog_id: UUID | None = None,
    visitor_hash: str | None = None,
) -> tuple[CompletionResult, AgentDialog]:
    """Load/create Postgres dialog keyed by client visitor id + draft id.

    ``visitor_hash`` (same as chat sessions) is stored/refreshed for correlation
    with IP-bound analytics — ownership stays on ``client_visitor_id``.
    """
    draft_key = (client_draft_id or "").strip()
    if not draft_key:
        raise MessageValidationError("client_draft_id обязателен для сохранения диалога.")
    if len(draft_key) > 64:
        raise MessageValidationError("client_draft_id слишком длинный.")
    owner = (client_visitor_id or "").strip().lower()
    if not owner:
        raise MessageValidationError("client_visitor_id обязателен для сохранения диалога.")
    vhash = (visitor_hash or "").strip() or None

    now = datetime.now(UTC)
    dialog: AgentDialog | None = None
    if dialog_id is not None:
        dialog = await dialogs.get(dialog_id)
        if dialog is None or dialog.client_visitor_id != owner:
            dialog = None
    if dialog is None:
        dialog = await dialogs.get_by_client_draft(
            client_visitor_id=owner, client_draft_id=draft_key
        )
    if dialog is None:
        dialog = AgentDialog(
            id=uuid4(),
            client_visitor_id=owner,
            visitor_hash=vhash,
            client_draft_id=draft_key,
            name=(definition.name or "").strip()[:120],
            system_prompt=definition.system_prompt.strip(),
            preferred_model=(definition.preferred_model or AUTO_MODEL).strip() or AUTO_MODEL,
            temperature=definition.temperature,
            max_tokens=definition.max_tokens,
            messages=[],
            created_at=now,
            updated_at=now,
        )
    else:
        dialog.name = (definition.name or "").strip()[:120]
        dialog.system_prompt = definition.system_prompt.strip()
        dialog.preferred_model = (
            (definition.preferred_model or AUTO_MODEL).strip() or AUTO_MODEL
        )
        dialog.temperature = definition.temperature
        dialog.max_tokens = definition.max_tokens
        if vhash:
            dialog.visitor_hash = vhash

    history = list(dialog.messages)
    result = await run_agent(
        definition=definition,
        message=message,
        router=router,
        enabled=enabled,
        max_message_chars=max_message_chars,
        generation=generation,
        history=history,
    )

    user_msg = AgentDialogMessage(
        id=str(uuid4()),
        role="user",
        content=message.strip(),
        created_at=now,
        model_id=None,
    )
    assistant_msg = AgentDialogMessage(
        id=str(uuid4()),
        role="assistant",
        content=result.content,
        created_at=datetime.now(UTC),
        model_id=result.model_id,
    )
    dialog.messages = [*history, user_msg, assistant_msg][-MAX_STORED_MESSAGES:]
    dialog.updated_at = datetime.now(UTC)
    saved = await dialogs.save(dialog)
    return result, saved
