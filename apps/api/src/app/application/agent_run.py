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
)
from app.domain.context_strategies import (
    ContextMode,
    ContextState,
    StrategyMeta,
    assemble_context,
    resolve_context_mode,
)
from app.domain.context_strategies.facts import (
    build_facts_extract_prompt,
    merge_facts,
    parse_facts_json,
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

FACTS_EXTRACT_SYSTEM = (
    "Ты обновляешь словарь фактов диалога. Отвечай только JSON-объектом, без markdown."
)


@dataclass(frozen=True, slots=True)
class AgentRunOutcome:
    result: CompletionResult
    tokens: TokenBreakdown
    compression: CompressionInfo | None = None
    strategy: StrategyMeta | None = None


def merge_system_extra(system_prompt: str, system_extra: str) -> str:
    sys = system_prompt.strip()
    extra = (system_extra or "").strip()
    if not extra:
        return sys
    return f"{sys}\n\n---\n{extra}"


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
    system_extra: str = "",
) -> AgentRunOutcome:
    if not enabled:
        raise AgentsRunDisabledError("Запуск агентов отключён конфигурацией.")
    validate_agent_run(definition, message=message, max_message_chars=max_message_chars)

    system_for_llm = merge_system_extra(definition.system_prompt.strip(), system_extra)
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


async def _extract_facts(
    *,
    router: ChatRouter,
    preferred_model: str,
    prior: dict[str, str],
    user_message: str,
) -> dict[str, str] | None:
    prompt = build_facts_extract_prompt(prior=prior, user_message=user_message)
    turns = [
        ChatMessage(role=MessageRole.SYSTEM, content=FACTS_EXTRACT_SYSTEM),
        ChatMessage(role=MessageRole.USER, content=prompt),
    ]
    gen = GenerationParams(temperature=0.1, max_tokens=400)
    result = await router.complete_chat(
        turns, preferred_model=preferred_model, generation=gen
    )
    return parse_facts_json(result.content or "")


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
    context_mode: str | None = None,
    compress: bool | None = None,
    recent_keep: int | None = None,
    summarize_every: int | None = None,
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
    mode = resolve_context_mode(context_mode=context_mode, compress=compress)

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
            facts={},
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
    state = ContextState(
        summary_text=dialog.summary_text or "",
        summary_until_count=int(dialog.summary_until_count or 0),
        facts=dict(dialog.facts or {}),
    )

    facts_updated = False
    if mode == ContextMode.FACTS:
        patch = await _extract_facts(
            router=router,
            preferred_model=dialog.preferred_model,
            prior=state.facts,
            user_message=message.strip(),
        )
        if patch is not None:
            state.facts = merge_facts(state.facts, patch)
            dialog.facts = dict(state.facts)
            facts_updated = True

    keep = recent_keep if recent_keep is not None else (
        DEFAULT_RECENT_KEEP if mode == ContextMode.COMPRESS else None
    )
    every = (
        summarize_every
        if summarize_every is not None
        else (DEFAULT_SUMMARIZE_EVERY if mode == ContextMode.COMPRESS else None)
    )

    assembly = assemble_context(
        history,
        mode=mode,
        state=state,
        system_prompt=definition.system_prompt.strip(),
        user_message=message.strip(),
        recent_keep=keep,
        summarize_every=every,
        facts_updated=facts_updated,
    )

    if mode == ContextMode.COMPRESS and assembly.needs_summary_refresh:
        summary_text = await _refresh_summary(
            router=router,
            preferred_model=dialog.preferred_model,
            prior_summary=state.summary_text,
            chunk=list(assembly.summary_chunk),
        )
        covered = len(history) - len(assembly.history)
        dialog.summary_text = summary_text
        dialog.summary_until_count = covered
        state.summary_text = summary_text
        state.summary_until_count = covered
        assembly = assemble_context(
            history,
            mode=mode,
            state=state,
            system_prompt=definition.system_prompt.strip(),
            user_message=message.strip(),
            recent_keep=keep,
            summarize_every=every,
        )
        meta = StrategyMeta(
            mode=assembly.meta.mode,
            recent_kept=assembly.meta.recent_kept,
            dropped=assembly.meta.dropped,
            facts=dict(assembly.meta.facts),
            facts_updated=assembly.meta.facts_updated,
            summary_used=bool(summary_text.strip()),
            summary_refreshed=True,
            tokens_raw_est=assembly.meta.tokens_raw_est,
            tokens_strategy_est=assembly.meta.tokens_strategy_est,
            covered_by_summary=covered,
            summary_text=summary_text,
        )
    else:
        meta = assembly.meta

    compression: CompressionInfo | None = None
    if mode == ContextMode.COMPRESS:
        compression = CompressionInfo(
            enabled=True,
            summary_used=meta.summary_used,
            summary_refreshed=meta.summary_refreshed,
            summary_text=meta.summary_text,
            recent_kept=meta.recent_kept,
            covered_by_summary=meta.covered_by_summary,
            tokens_raw_est=meta.tokens_raw_est,
            tokens_compressed_est=meta.tokens_strategy_est,
        )

    outcome = await run_agent(
        definition=definition,
        message=message,
        router=router,
        enabled=enabled,
        max_message_chars=max_message_chars,
        generation=generation,
        history=assembly.history,
        context_limit=context_limit,
        system_extra=assembly.system_extra,
    )
    outcome = AgentRunOutcome(
        result=outcome.result,
        tokens=outcome.tokens,
        compression=compression,
        strategy=meta if mode != ContextMode.NONE else meta,
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
