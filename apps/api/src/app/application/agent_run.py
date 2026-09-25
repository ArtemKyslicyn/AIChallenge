"""Run agent with optional prior turns; persist dialog turns in Postgres."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from app.domain.agent_definition import AgentDefinition, validate_agent_run
from app.domain.agent_dialog import AgentDialog, AgentDialogMessage
from app.domain.agent_memory import (
    LongTermMemory,
    WorkingMemory,
    build_memory_system_extra,
)
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
from app.domain.invariants import (
    build_refusal_reply,
    find_invariant_conflicts,
    format_invariants_block,
    parse_invariants,
)
from app.domain.mcp_catalog import McpToolCall, McpToolRunner
from app.domain.media import ToolCallRequest
from app.domain.personalization import (
    PreferenceProfile,
    build_personalization_extra,
    get_expert_lens,
)
from app.domain.ports import AgentDialogRepository, ChatRouter
from app.domain.task_state import (
    build_skip_refusal,
    find_task_skip_conflicts,
    format_task_state_block,
)
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
    invariant_conflict: bool = False
    task_skip_conflict: bool = False
    mcp_calls: tuple[McpToolCall, ...] = ()


def merge_system_extra(system_prompt: str, system_extra: str) -> str:
    sys = system_prompt.strip()
    extra = (system_extra or "").strip()
    if not extra:
        return sys
    return f"{sys}\n\n---\n{extra}"


_PULSE_HINT = re.compile(
    r"(?i)пульс|здоров|health|рейтинг|сводк|digest|probe_stand|model_pulse|"
    r"ranking|расписан|schedule|pareto|статус стенда|проверь стенд|"
    r"вахт|инцидент|watch_brief|дежур|пайплайн|цепочк|ночной бриф|saveToFile|summarize"
)


def detect_pulse_intent(text: str, available: set[str]) -> tuple[str, dict[str, Any]] | None:
    clean = text or ""
    if "Результат MCP" in clean:
        return None
    if re.search(r"(?i)разбор смены|orchestration|несколько сервер", clean):
        if "watch_brief" in available:
            return "watch_brief", {}
    if not _PULSE_HINT.search(clean):
        return None
    if re.search(r"(?i)пайплайн|цепочк|ночной бриф|saveToFile|архив бриф", clean):
        if "search" in available:
            return "search", {"hours": 24}
    if re.search(r"(?i)вахт|инцидент|watch_brief|дежур", clean) and "watch_brief" in available:
        return "watch_brief", {}
    if re.search(r"(?i)расписан|schedule_digest|каждые", clean) and "schedule_digest" in available:
        seconds = 60
        match = re.search(r"(\d+)\s*(?:сек|sec|с\b)", clean) or re.search(r"каждые\s+(\d+)", clean)
        if match:
            seconds = int(match.group(1))
        return "schedule_digest", {
            "interval_seconds": max(30, seconds),
            "hours": 24,
            "note": "from-agent",
        }
    if re.search(r"(?i)рейтинг|ranking|pareto|model_pulse|качество модел", clean):
        if "model_pulse" in available:
            hours = 24
            match = re.search(r"(\d+)\s*(?:ч|час|h)", clean)
            if match:
                hours = int(match.group(1))
            return "model_pulse", {"hours": hours}
    if re.search(r"(?i)сводк|digest|latest_digest", clean) and "latest_digest" in available:
        return "latest_digest", {}
    if "probe_stand" in available:
        return "probe_stand", {}
    return None


def _openai_tool_names(tools: list[dict[str, object]]) -> set[str]:
    names: set[str] = set()
    for item in tools:
        fn = item.get("function") if isinstance(item, dict) else None
        if isinstance(fn, dict) and fn.get("name"):
            names.add(str(fn["name"]))
        elif isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    return names


MAX_MCP_ROUNDS = 6
_PIPELINE_NEXT = {"search": "summarize", "summarize": "saveToFile"}
_SHIFT_HINT = re.compile(r"(?i)разбор смены|orchestration|несколько сервер")
_SHIFT_ORDER = ("watch_brief", "model_pulse", "search", "summarize", "saveToFile")


def _tool_servers(tools: list[dict[str, object]]) -> dict[str, str]:
    servers: dict[str, str] = {}
    for item in tools:
        fn = item.get("function") if isinstance(item, dict) else None
        source = fn if isinstance(fn, dict) else item
        if not isinstance(source, dict) or not source.get("name"):
            continue
        desc = str(source.get("description") or "")
        if desc.startswith("[") and "]" in desc:
            servers[str(source["name"])] = desc[1 : desc.index("]")]
    return servers


def _next_shift_step(
    executed: list[McpToolCall], available: set[str]
) -> tuple[str, dict[str, Any]] | None:
    done = {call.name for call in executed}
    for step in _SHIFT_ORDER:
        if step in done or step not in available:
            continue
        if step == "model_pulse":
            return step, {"hours": 24}
        if step == "search":
            return step, {"hours": 24}
        if step == "summarize":
            prev = next((call.result for call in reversed(executed) if call.name == "search"), "")
            return step, {"payload": prev}
        if step == "saveToFile":
            prev = next(
                (call.result for call in reversed(executed) if call.name == "summarize"), ""
            )
            return step, {"brief": prev, "name": "shift-review"}
        return step, {}
    return None


def _continue_pipeline(last: McpToolCall, available: set[str]) -> tuple[str, dict[str, Any]] | None:
    nxt = _PIPELINE_NEXT.get(last.name)
    if not nxt or nxt not in available:
        return None
    if nxt == "summarize":
        return nxt, {"payload": last.result}
    return nxt, {"brief": last.result, "name": "night-brief"}


def _followup_user_message(calls: list[McpToolCall]) -> str:
    blocks = [f"Результат MCP {call.name}:\n{call.result}" for call in calls]
    return (
        "\n\n".join(blocks)
        + "\n\nЕсли пайплайн не закончен — вызови следующую ступень и передай JSON. "
        "Иначе ответь оператору по фактам, без выдумки."
    )


async def _run_mcp_round(
    *,
    router: ChatRouter,
    turns: list[ChatMessage],
    preferred: str,
    generation: GenerationParams | None,
    result: CompletionResult,
    mcp_runner: McpToolRunner,
    tools: list[dict[str, object]],
    user_message: str,
) -> tuple[CompletionResult, tuple[McpToolCall, ...]]:
    names = _openai_tool_names(tools)
    servers = _tool_servers(tools)
    shift = bool(_SHIFT_HINT.search(user_message))
    conversation = list(turns)
    current = result
    executed: list[McpToolCall] = []
    for round_index in range(MAX_MCP_ROUNDS):
        requested = list(current.tool_calls or [])
        if not requested and round_index == 0:
            intent = detect_pulse_intent(user_message, names)
            if intent is not None:
                name, arguments = intent
                requested = [ToolCallRequest(id="pulse-intent", name=name, arguments=arguments)]
        if not requested and executed:
            nxt = (
                _next_shift_step(executed, names)
                if shift
                else _continue_pipeline(executed[-1], names)
            )
            if nxt is not None:
                name, arguments = nxt
                requested = [ToolCallRequest(id="pulse-pipeline", name=name, arguments=arguments)]
        if not requested:
            break
        batch: list[McpToolCall] = []
        for call in requested[:3]:
            raw = await mcp_runner.call_tool(call.name, dict(call.arguments or {}))
            item = McpToolCall(
                name=call.name,
                arguments=dict(call.arguments or {}),
                result=raw,
                server=servers.get(call.name, ""),
            )
            batch.append(item)
            executed.append(item)
        if not batch:
            break
        nxt = _next_shift_step(executed, names) if shift else _continue_pipeline(batch[-1], names)
        if nxt is not None:
            name, arguments = nxt
            current = CompletionResult(
                content=current.content or "",
                model_id=current.model_id,
                tool_calls=[ToolCallRequest(id="pulse-pipeline", name=name, arguments=arguments)],
            )
            continue
        conversation = [
            *conversation,
            ChatMessage(
                role=MessageRole.ASSISTANT,
                content=current.content or f"Вызвал {', '.join(item.name for item in batch)}",
            ),
            ChatMessage(role=MessageRole.USER, content=_followup_user_message(batch)),
        ]
        current = await router.complete_chat(
            conversation,
            preferred_model=preferred,
            generation=generation,
            tools=tools,
        )
    return current, tuple(executed)


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
    mcp_runner: McpToolRunner | None = None,
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
    tools: list[dict[str, object]] | None = None
    if mcp_runner is not None:
        listed = await mcp_runner.openai_tools()
        tools = listed or None
    result = await router.complete_chat(
        turns, preferred_model=preferred, generation=generation, tools=tools
    )
    mcp_calls: tuple[McpToolCall, ...] = ()
    if mcp_runner is not None and tools:
        result, mcp_calls = await _run_mcp_round(
            router=router,
            turns=turns,
            preferred=preferred,
            generation=generation,
            result=result,
            mcp_runner=mcp_runner,
            tools=tools,
            user_message=message.strip(),
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
    return AgentRunOutcome(result=result, tokens=tokens, mcp_calls=mcp_calls)


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
    result = await router.complete_chat(turns, preferred_model=preferred_model, generation=gen)
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
    result = await router.complete_chat(turns, preferred_model=preferred_model, generation=gen)
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
    long_term: LongTermMemory | None = None,
    include_working_memory: bool = True,
    include_long_term_memory: bool = True,
    preference: PreferenceProfile | None = None,
    expert_lens_id: str | None = None,
    task_just_resumed: bool = False,
    mcp_runner: McpToolRunner | None = None,
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
    lens = get_expert_lens(expert_lens_id)

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
            working_memory={},
            created_at=now,
            updated_at=now,
        )
    else:
        dialog.name = (definition.name or "").strip()[:120]
        dialog.system_prompt = definition.system_prompt.strip()
        dialog.preferred_model = (definition.preferred_model or AUTO_MODEL).strip() or AUTO_MODEL
        dialog.temperature = definition.temperature
        dialog.max_tokens = definition.max_tokens
        if vhash:
            dialog.visitor_hash = vhash

    history = list(dialog.messages)
    working_preview = WorkingMemory.from_mapping(dialog.working_memory)
    skip_hits = find_task_skip_conflicts(working_preview.task, message)
    if skip_hits:
        refusal = build_skip_refusal(skip_hits, message.strip())
        _, truncation = fit_history_to_budget(
            system_prompt=definition.system_prompt.strip(),
            history=history,
            user_message=message.strip(),
            context_limit=context_limit,
            max_tokens=definition.max_tokens
            if definition.max_tokens is not None
            else (generation.max_tokens if generation else None),
        )
        tokens = build_token_breakdown(
            system_prompt=definition.system_prompt.strip(),
            history_before=history,
            history_after=history,
            user_message=message.strip(),
            completion=refusal,
            model_id="task-fsm",
            truncation=truncation,
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
            content=refusal,
            created_at=datetime.now(UTC),
            model_id="task-fsm",
        )
        dialog.messages = [*history, user_msg, assistant_msg][-MAX_STORED_MESSAGES:]
        dialog.updated_at = datetime.now(UTC)
        saved = await dialogs.save(dialog)
        return (
            AgentRunOutcome(
                result=CompletionResult(content=refusal, model_id="task-fsm"),
                tokens=tokens,
                task_skip_conflict=True,
            ),
            saved,
        )

    inv_items = parse_invariants(dialog.invariants)
    conflicts = find_invariant_conflicts(inv_items, message)
    if conflicts:
        refusal = build_refusal_reply(conflicts, message.strip())
        _, truncation = fit_history_to_budget(
            system_prompt=definition.system_prompt.strip(),
            history=history,
            user_message=message.strip(),
            context_limit=context_limit,
            max_tokens=definition.max_tokens
            if definition.max_tokens is not None
            else (generation.max_tokens if generation else None),
        )
        tokens = build_token_breakdown(
            system_prompt=definition.system_prompt.strip(),
            history_before=history,
            history_after=history,
            user_message=message.strip(),
            completion=refusal,
            model_id="invariants",
            truncation=truncation,
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
            content=refusal,
            created_at=datetime.now(UTC),
            model_id="invariants",
        )
        dialog.messages = [*history, user_msg, assistant_msg][-MAX_STORED_MESSAGES:]
        dialog.updated_at = datetime.now(UTC)
        saved = await dialogs.save(dialog)
        return (
            AgentRunOutcome(
                result=CompletionResult(content=refusal, model_id="invariants"),
                tokens=tokens,
                invariant_conflict=True,
            ),
            saved,
        )

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

    keep = (
        recent_keep
        if recent_keep is not None
        else (DEFAULT_RECENT_KEEP if mode == ContextMode.COMPRESS else None)
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

    working = WorkingMemory.from_mapping(dialog.working_memory)
    # Order: LTM identity → preferences → lens → working
    identity_extra = build_memory_system_extra(
        working=None,
        long_term=long_term or LongTermMemory(),
        include_working=False,
        include_long_term=include_long_term_memory,
        include_short_term=False,
    )
    pers_extra = build_personalization_extra(preference=preference, lens=lens)
    working_extra = build_memory_system_extra(
        working=working,
        long_term=None,
        include_working=include_working_memory,
        include_long_term=False,
        include_short_term=False,
    )
    memory_parts = [p for p in (identity_extra, pers_extra, working_extra) if p]
    task_extra = format_task_state_block(
        working.task,
        just_resumed=bool(task_just_resumed) and not working.task.paused,
    )
    if task_extra:
        memory_parts.append(task_extra)
    inv_extra = format_invariants_block(inv_items)
    if inv_extra:
        memory_parts.append(inv_extra)
    memory_extra = "\n\n".join(memory_parts)
    system_extra = assembly.system_extra
    if memory_extra:
        system_extra = f"{system_extra}\n\n{memory_extra}".strip() if system_extra else memory_extra

    if expert_lens_id:
        dialog.active_lens_id = lens.id
    elif dialog.active_lens_id is None and lens.id != "neutral":
        dialog.active_lens_id = lens.id

    outcome = await run_agent(
        definition=definition,
        message=message,
        router=router,
        enabled=enabled,
        max_message_chars=max_message_chars,
        generation=generation,
        history=assembly.history,
        context_limit=context_limit,
        system_extra=system_extra,
        mcp_runner=mcp_runner,
    )
    outcome = AgentRunOutcome(
        result=outcome.result,
        tokens=outcome.tokens,
        compression=compression,
        strategy=meta if mode != ContextMode.NONE else meta,
        mcp_calls=outcome.mcp_calls,
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
