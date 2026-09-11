"""Run agent with optional prior turns; persist dialog turns in Postgres."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.agent_definition import AgentDefinition, validate_agent_run
from app.domain.agent_dialog import AgentDialog, AgentDialogMessage
from app.domain.context_compress import (
    DEFAULT_RECENT_KEEP,
    DEFAULT_SUMMARIZE_EVERY,
    CompressionInfo,
    build_summarizer_prompt,
    estimate_compressed_request_tokens,
    estimate_raw_request_tokens,
    merge_system_with_summary,
    plan_compression,
)
from app.domain.entities import AUTO_MODEL, ChatMessage, CompletionResult, MessageRole
from app.domain.errors import AgentsRunDisabledError, MessageValidationError
from app.domain.generation import GenerationParams
from app.domain.ports import AgentDialogRepository, ChatRouter
from app.domain.token_meter import (
    TokenBreakdown,
    build_token_breakdown,
    fit_history_to_budget,
    history_to_chat_turns,
)

#: Soft cap so context / JSONB stay bounded.
MAX_STORED_MESSAGES = 80
DEFAULT_CONTEXT_LIMIT = 8192

SUMMARIZER_SYSTEM = (
    "Ты сжимаешь историю диалога в краткую сводку. "
    "Сохраняй факты, имена, решения и открытые вопросы. Без преамбулы."
)


@dataclass(frozen=True, slots=True)
class AgentRunOutcome:
    result: CompletionResult
    tokens: TokenBreakdown
    compression: CompressionInfo | None = None


async def run_agent(
    *,
    definition: AgentDefinition,
    message: str,
    router: ChatRouter,
    enabled: bool,
    max_message_chars: int,
    generation: GenerationParams | None = None,
    history: list[AgentDialogMessage] | None = None,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    context_summary: str = "",
) -> AgentRunOutcome:
    if not enabled:
        raise AgentsRunDisabledError("Запуск агентов отключён конфигурацией.")
    validate_agent_run(definition, message=message, max_message_chars=max_message_chars)

    system_for_llm = merge_system_with_summary(
        definition.system_prompt.strip(), context_summary
    )
    history_before = list(history or [])
    history_after, truncation = fit_history_to_budget(
        system_prompt=system_for_llm,
        history=history_before,
        user_message=message.strip(),
        context_limit=context_limit,
        max_tokens=definition.max_tokens
        if definition.max_tokens is not None
        else (generation.max_tokens if generation else None),
    )

    turns: list[ChatMessage] = [
        ChatMessage(role=MessageRole.SYSTEM, content=system_for_llm),
        *history_to_chat_turns(history_after),
        ChatMessage(role=MessageRole.USER, content=message.strip()),
    ]

    preferred = (definition.preferred_model or AUTO_MODEL).strip() or AUTO_MODEL
    result = await router.complete_chat(
        turns, preferred_model=preferred, generation=generation
    )
    tokens = build_token_breakdown(
        system_prompt=system_for_llm,
        history_before=history_before,
        history_after=history_after,
        user_message=message.strip(),
        completion=result.content,
        model_id=result.model_id,
        truncation=truncation,
    )
    return AgentRunOutcome(result=result, tokens=tokens)


async def _refresh_summary(
    *,
    router: ChatRouter,
    preferred_model: str,
    prior_summary: str,
    chunk: list[AgentDialogMessage],
) -> str:
    prompt = build_summarizer_prompt(prior_summary=prior_summary, chunk=chunk)
    turns = [
        ChatMessage(role=MessageRole.SYSTEM, content=SUMMARIZER_SYSTEM),
        ChatMessage(role=MessageRole.USER, content=prompt),
    ]
    gen = GenerationParams(temperature=0.2, max_tokens=400)
    result = await router.complete_chat(
        turns, preferred_model=preferred_model, generation=gen
    )
    return (result.content or "").strip()


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
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
    compress: bool = False,
    recent_keep: int = DEFAULT_RECENT_KEEP,
    summarize_every: int = DEFAULT_SUMMARIZE_EVERY,
) -> tuple[AgentRunOutcome, AgentDialog]:
    """Load/create Postgres dialog keyed by client visitor id + draft id."""
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
            summary_text="",
            summary_until_count=0,
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
    compression: CompressionInfo | None = None
    llm_history = history
    context_summary = ""

    if compress:
        plan = plan_compression(
            history,
            summary_until_count=dialog.summary_until_count,
            recent_keep=recent_keep,
            summarize_every=summarize_every,
        )
        refreshed = False
        summary_text = dialog.summary_text or ""
        covered = dialog.summary_until_count
        if plan.needs_refresh and plan.to_summarize:
            summary_text = await _refresh_summary(
                router=router,
                preferred_model=dialog.preferred_model,
                prior_summary=summary_text,
                chunk=plan.to_summarize,
            )
            covered = len(history) - len(plan.recent)
            dialog.summary_text = summary_text
            dialog.summary_until_count = covered
            refreshed = True
        llm_history = plan.recent
        context_summary = summary_text
        raw_est = estimate_raw_request_tokens(
            system_prompt=definition.system_prompt.strip(),
            messages=history,
            user_message=message.strip(),
        )
        compressed_est = estimate_compressed_request_tokens(
            system_prompt=definition.system_prompt.strip(),
            summary_text=summary_text,
            recent=llm_history,
            user_message=message.strip(),
        )
        compression = CompressionInfo(
            enabled=True,
            summary_used=bool(summary_text.strip()),
            summary_refreshed=refreshed,
            summary_text=summary_text,
            recent_kept=len(llm_history),
            covered_by_summary=covered,
            tokens_raw_est=raw_est,
            tokens_compressed_est=compressed_est,
        )

    outcome = await run_agent(
        definition=definition,
        message=message,
        router=router,
        enabled=enabled,
        max_message_chars=max_message_chars,
        generation=generation,
        history=llm_history,
        context_limit=context_limit,
        context_summary=context_summary,
    )
    if compression is not None:
        outcome = AgentRunOutcome(
            result=outcome.result,
            tokens=outcome.tokens,
            compression=compression,
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
        content=outcome.result.content,
        created_at=datetime.now(UTC),
        model_id=outcome.result.model_id,
    )
    dialog.messages = [*history, user_msg, assistant_msg][-MAX_STORED_MESSAGES:]
    dialog.updated_at = datetime.now(UTC)
    saved = await dialogs.save(dialog)
    return outcome, saved
