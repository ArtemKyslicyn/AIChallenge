"""Agent workshop: definition + message → LLM; optional Postgres dialog memory."""

from __future__ import annotations

import logging
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.adapters.api.auth import OptionalAuthUser
from app.adapters.api.schemas import (
    AgentCompressionResponse,
    AgentContextStrategyResponse,
    AgentDialogForkRequest,
    AgentDialogMessageResponse,
    AgentDialogResponse,
    AgentInvariantEventRequest,
    AgentInvariantEventResponse,
    AgentMemorySnapshotResponse,
    AgentMemoryWriteRequest,
    AgentMemoryWriteResponse,
    AgentTaskEventRequest,
    AgentTaskEventResponse,
    AgentTokenTruncationResponse,
    AgentTokenUsageResponse,
    AgentWorkshopRunRequest,
    AgentWorkshopRunResponse,
)
from app.adapters.persistence.agent_dialog_repo import SqlAlchemyAgentDialogRepository
from app.adapters.persistence.long_term_memory_repo import SqlAlchemyLongTermMemoryRepository
from app.adapters.persistence.preference_repo import SqlAlchemyPreferenceProfileRepository
from app.application.agent_run import DEFAULT_CONTEXT_LIMIT, run_agent, run_agent_with_dialog
from app.application.dialog_fork import fork_agent_dialog
from app.application.invariants_ops import (
    apply_invariant_event_to_dialog,
    ensure_dialog_for_invariants,
)
from app.application.llm_catalog import generation_from_api
from app.application.task_fsm import apply_task_event_to_dialog, ensure_dialog_for_task
from app.core.deps import (
    ClientVisitorId,
    DbSession,
    get_container,
    resolve_visitor_identity,
    spawn_detached,
    visitor_id_header,
)
from app.domain.agent_definition import AgentDefinition
from app.domain.agent_dialog import AgentDialog, AgentDialogMessage
from app.domain.agent_memory import (
    LAYER_PURPOSE,
    MemoryLayer,
    MemoryWrite,
    WorkingMemory,
    apply_long_term_write,
    apply_working_write,
    describe_memory_write,
    parse_memory_chat_command,
)
from app.domain.analytics import AnalyticsEvent
from app.domain.context_compress import CompressionInfo
from app.domain.context_strategies import StrategyMeta
from app.domain.entities import AUTO_MODEL
from app.domain.errors import MessageValidationError
from app.domain.invariants import InvariantEvent, parse_invariant_chat_command
from app.domain.owner_key import memory_owner_key
from app.domain.task_state import TaskEvent, parse_task_chat_command
from app.domain.token_meter import TokenBreakdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-workshop", tags=["agent-workshop"])


def _definition_from_payload(payload: AgentWorkshopRunRequest) -> AgentDefinition:
    return AgentDefinition(
        name=(payload.definition.name or "").strip(),
        system_prompt=payload.definition.system_prompt,
        preferred_model=(payload.definition.preferred_model or AUTO_MODEL).strip() or AUTO_MODEL,
        temperature=payload.definition.temperature,
        max_tokens=payload.definition.max_tokens,
    )


def _msg_dto(m: AgentDialogMessage) -> AgentDialogMessageResponse:
    return AgentDialogMessageResponse(
        id=m.id,
        role=m.role,
        content=m.content,
        model_id=m.model_id,
        created_at=m.created_at.isoformat(),
    )


def _dialog_dto(dialog: AgentDialog) -> AgentDialogResponse:
    stamp = dialog.updated_at or dialog.created_at
    return AgentDialogResponse(
        id=dialog.id,
        client_draft_id=dialog.client_draft_id,
        name=dialog.name,
        messages=[_msg_dto(m) for m in dialog.messages],
        updated_at=stamp.isoformat() if stamp is not None else "",
        summary_text=dialog.summary_text or "",
        summary_until_count=int(dialog.summary_until_count or 0),
        facts=dict(dialog.facts or {}),
        working_memory=dict(dialog.working_memory or {}),
        invariants=list(dialog.invariants or []),
        parent_dialog_id=dialog.parent_dialog_id,
        branch_label=dialog.branch_label,
        forked_from_message_id=dialog.forked_from_message_id,
    )


def _tokens_dto(tokens: TokenBreakdown) -> AgentTokenUsageResponse:
    t = tokens.truncation
    return AgentTokenUsageResponse(
        request=tokens.request,
        history_before=tokens.history_before,
        history_after=tokens.history_after,
        completion=tokens.completion,
        total=tokens.total,
        cost_proxy=tokens.cost_proxy,
        truncation=AgentTokenTruncationResponse(
            applied=t.applied,
            dropped_messages=t.dropped_messages,
            dropped_tokens_est=t.dropped_tokens_est,
            context_limit=t.context_limit,
            budget=t.budget,
        ),
    )


def _compression_dto(info: CompressionInfo) -> AgentCompressionResponse:
    return AgentCompressionResponse(
        enabled=info.enabled,
        summary_used=info.summary_used,
        summary_refreshed=info.summary_refreshed,
        summary_text=info.summary_text,
        recent_kept=info.recent_kept,
        covered_by_summary=info.covered_by_summary,
        tokens_raw_est=info.tokens_raw_est,
        tokens_compressed_est=info.tokens_compressed_est,
    )


def _strategy_dto(meta: StrategyMeta) -> AgentContextStrategyResponse:
    return AgentContextStrategyResponse(
        mode=meta.mode.value,
        recent_kept=meta.recent_kept,
        dropped=meta.dropped,
        facts=dict(meta.facts or {}),
        facts_updated=meta.facts_updated,
        tokens_raw_est=meta.tokens_raw_est,
        tokens_strategy_est=meta.tokens_strategy_est,
        summary_used=meta.summary_used,
        summary_refreshed=meta.summary_refreshed,
        summary_text=meta.summary_text,
        covered_by_summary=meta.covered_by_summary,
    )


def _resolve_context_limit(raw: int | None) -> int:
    if raw is None:
        return DEFAULT_CONTEXT_LIMIT
    return max(64, min(128_000, int(raw)))


def _owner_key(visitor_id: str, auth_user: object | None) -> str:
    user_id = getattr(auth_user, "id", None) if auth_user is not None else None
    return memory_owner_key(visitor_id=visitor_id, user_id=user_id)


@router.post("/run", response_model=AgentWorkshopRunResponse)
async def run_workshop_agent(
    payload: AgentWorkshopRunRequest,
    request: Request,
    db: DbSession,
    auth_user: OptionalAuthUser,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> AgentWorkshopRunResponse:
    container = get_container(request)
    settings = container.settings
    visitor_key = client_visitor_id or "anonymous"
    container.agent_run_limiter.check_and_record(visitor_key)

    definition = _definition_from_payload(payload)
    generation = generation_from_api(
        temperature=payload.definition.temperature,
        max_tokens=payload.definition.max_tokens,
        stop=None,
        prompt_format=False,
        prompt_length=False,
        prompt_stop=False,
        reasoning=False,
    )
    t0 = time.perf_counter()
    status = "ok"
    model_id = ""
    content = ""
    dialog_id: UUID | None = None
    messages_out: list[AgentDialogMessageResponse] | None = None
    tokens_out: AgentTokenUsageResponse | None = None
    compression_out: AgentCompressionResponse | None = None
    strategy_out: AgentContextStrategyResponse | None = None
    ctx_limit = _resolve_context_limit(payload.context_limit)
    task_just_resumed = False
    try:
        if payload.persist:
            visitor = (client_visitor_id or "").strip().lower()
            if not visitor:
                raise MessageValidationError(
                    "Для сохранения диалога нужен заголовок X-Visitor-Id (client id)."
                )
            owner = memory_owner_key(
                visitor_id=visitor,
                user_id=auth_user.id if auth_user is not None else None,
            )
            draft_id = (payload.client_draft_id or "").strip()
            if not draft_id:
                raise MessageValidationError("Для сохранения диалога передайте client_draft_id.")
            identity = resolve_visitor_identity(request, visitor)
            vhash = identity[0] if identity else None
            dialogs = SqlAlchemyAgentDialogRepository(db)

            task_ev = parse_task_chat_command(payload.message)
            if task_ev is not None:
                dialog = await ensure_dialog_for_task(
                    dialogs,
                    owner_key=owner,
                    client_draft_id=draft_id,
                    dialog_name=definition.name,
                    dialog_system_prompt=definition.system_prompt,
                )
                if vhash and not dialog.visitor_hash:
                    dialog.visitor_hash = vhash
                dialog, label = await apply_task_event_to_dialog(dialog, task_ev, dialogs=dialogs)
                if task_ev.skip_llm:
                    from datetime import UTC, datetime
                    from uuid import uuid4

                    now = datetime.now(UTC)
                    ack = f"✓ Задача · {label}"
                    dialog.messages = [
                        *dialog.messages,
                        AgentDialogMessage(
                            id=str(uuid4()),
                            role="user",
                            content=payload.message.strip(),
                            created_at=now,
                            model_id=None,
                        ),
                        AgentDialogMessage(
                            id=str(uuid4()),
                            role="assistant",
                            content=ack,
                            created_at=now,
                            model_id="task-fsm",
                        ),
                    ][-80:]
                    dialog.updated_at = now
                    dialog = await dialogs.save(dialog)
                    await db.commit()
                    return AgentWorkshopRunResponse(
                        content=ack,
                        model_id="task-fsm",
                        dialog_id=dialog.id,
                        messages=[_msg_dto(m) for m in dialog.messages],
                    )
                await db.commit()
                task_just_resumed = task_ev.name == "resume"
                # Continue into LLM with updated state (start/advance/resume).

            inv_ev = parse_invariant_chat_command(payload.message)
            if inv_ev is not None:
                dialog = await ensure_dialog_for_invariants(
                    dialogs,
                    owner_key=owner,
                    client_draft_id=draft_id,
                    dialog_name=definition.name,
                    dialog_system_prompt=definition.system_prompt,
                )
                if vhash and not dialog.visitor_hash:
                    dialog.visitor_hash = vhash
                dialog, label = await apply_invariant_event_to_dialog(
                    dialog, inv_ev, dialogs=dialogs
                )
                if inv_ev.skip_llm:
                    from datetime import UTC, datetime
                    from uuid import uuid4

                    now = datetime.now(UTC)
                    ack = f"✓ Инварианты · {label}"
                    dialog.messages = [
                        *dialog.messages,
                        AgentDialogMessage(
                            id=str(uuid4()),
                            role="user",
                            content=payload.message.strip(),
                            created_at=now,
                            model_id=None,
                        ),
                        AgentDialogMessage(
                            id=str(uuid4()),
                            role="assistant",
                            content=ack,
                            created_at=now,
                            model_id="invariants",
                        ),
                    ][-80:]
                    dialog.updated_at = now
                    dialog = await dialogs.save(dialog)
                    await db.commit()
                    return AgentWorkshopRunResponse(
                        content=ack,
                        model_id="invariants",
                        dialog_id=dialog.id,
                        messages=[_msg_dto(m) for m in dialog.messages],
                        invariants=list(dialog.invariants or []),
                    )

            preference = await SqlAlchemyPreferenceProfileRepository(db).get_active(owner)
            lens_id = (payload.expert_lens_id or "").strip() or None
            outcome, dialog = await run_agent_with_dialog(
                definition=definition,
                message=payload.message,
                router=container.router,
                dialogs=dialogs,
                client_visitor_id=owner,
                client_draft_id=draft_id,
                enabled=settings.agents_run_enabled,
                max_message_chars=settings.max_message_chars,
                generation=generation,
                dialog_id=payload.dialog_id,
                visitor_hash=vhash,
                context_limit=ctx_limit,
                context_mode=payload.context_mode,
                compress=bool(payload.compress) if payload.compress else None,
                recent_keep=payload.recent_keep,
                summarize_every=payload.summarize_every,
                long_term=await SqlAlchemyLongTermMemoryRepository(db).get(owner),
                include_working_memory=payload.include_working_memory,
                include_long_term_memory=payload.include_long_term_memory,
                preference=preference,
                expert_lens_id=lens_id,
                task_just_resumed=task_just_resumed,
            )
            await db.commit()
            content = outcome.result.content
            model_id = outcome.result.model_id
            dialog_id = dialog.id
            messages_out = [_msg_dto(m) for m in dialog.messages]
            tokens_out = _tokens_dto(outcome.tokens)
            if outcome.compression is not None:
                compression_out = _compression_dto(outcome.compression)
            if outcome.strategy is not None:
                strategy_out = _strategy_dto(outcome.strategy)
            return AgentWorkshopRunResponse(
                content=content,
                model_id=model_id,
                dialog_id=dialog_id,
                messages=messages_out,
                tokens=tokens_out,
                compression=compression_out,
                context_strategy=strategy_out,
                invariant_conflict=bool(outcome.invariant_conflict),
                invariants=list(dialog.invariants or []),
            )

        outcome = await run_agent(
            definition=definition,
            message=payload.message,
            router=container.router,
            enabled=settings.agents_run_enabled,
            max_message_chars=settings.max_message_chars,
            generation=generation,
            context_limit=ctx_limit,
        )
        content = outcome.result.content
        model_id = outcome.result.model_id
        tokens_out = _tokens_dto(outcome.tokens)
        return AgentWorkshopRunResponse(content=content, model_id=model_id, tokens=tokens_out)
    except Exception:
        status = "error"
        await db.rollback()
        raise
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)

        async def _emit() -> None:
            try:
                name = "agent_run_completed" if status == "ok" else "agent_run_failed"
                props = {
                    "status": status,
                    "model_id": model_id or None,
                    "preferred_model": definition.preferred_model,
                    "latency_ms": latency_ms,
                    "answer_chars": len(content),
                    "agent_name": definition.name or None,
                    "system_prompt_chars": len(definition.system_prompt or ""),
                    "message_chars": len(payload.message or ""),
                    "persist": bool(payload.persist),
                    "dialog_id": str(dialog_id) if dialog_id else None,
                    "client_visitor_id": client_visitor_id,
                    "context_limit": ctx_limit,
                }
                if tokens_out is not None:
                    props["tokens_total"] = tokens_out.total
                    props["tokens_request"] = tokens_out.request
                    props["truncated"] = tokens_out.truncation.applied
                await container.analytics.capture(
                    [
                        AnalyticsEvent(
                            name=name,
                            distinct_id=visitor_key,
                            properties=props,
                        )
                    ]
                )
            except Exception:  # noqa: BLE001 — analytics is fail-open
                logger.debug("agent_run analytics failed", exc_info=True)

        spawn_detached(_emit())


@router.get(
    "/dialogs/by-draft/{client_draft_id}",
    response_model=AgentDialogResponse,
    responses={404: {"description": "no dialog yet"}},
)
async def get_dialog_by_draft(
    client_draft_id: str,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    auth_user: OptionalAuthUser,
) -> AgentDialogResponse:
    """Reload dialog for this browser client id + draft."""
    key = (client_draft_id or "").strip()
    if not key:
        raise MessageValidationError("client_draft_id пуст.")
    owner = _owner_key(client_visitor_id, auth_user)
    repo = SqlAlchemyAgentDialogRepository(db)
    dialog = await repo.get_by_client_draft(client_visitor_id=owner, client_draft_id=key)
    if dialog is None and owner != client_visitor_id:
        dialog = await repo.get_by_client_draft(
            client_visitor_id=client_visitor_id, client_draft_id=key
        )
    if dialog is None:
        raise HTTPException(status_code=404, detail="Диалог не найден.")
    return _dialog_dto(dialog)


@router.post("/dialogs/by-draft/{client_draft_id}/clear", response_model=AgentDialogResponse)
async def clear_dialog_by_draft(
    client_draft_id: str,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    auth_user: OptionalAuthUser,
) -> AgentDialogResponse:
    """Wipe stored turns but keep the dialog row (definition stays)."""
    from datetime import UTC, datetime

    key = (client_draft_id or "").strip()
    owner = _owner_key(client_visitor_id, auth_user)
    repo = SqlAlchemyAgentDialogRepository(db)
    dialog = await repo.get_by_client_draft(client_visitor_id=owner, client_draft_id=key)
    if dialog is None and owner != client_visitor_id:
        dialog = await repo.get_by_client_draft(
            client_visitor_id=client_visitor_id, client_draft_id=key
        )
    if dialog is None:
        raise MessageValidationError("Диалог ещё не создан — нечего очищать.")
    dialog.messages = []
    dialog.summary_text = ""
    dialog.summary_until_count = 0
    dialog.facts = {}
    dialog.working_memory = {}
    dialog.updated_at = datetime.now(UTC)
    saved = await repo.save(dialog)
    await db.commit()
    return _dialog_dto(saved)


@router.get("/memory", response_model=AgentMemorySnapshotResponse)
async def get_memory_snapshot(
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    auth_user: OptionalAuthUser,
    client_draft_id: str | None = None,
) -> AgentMemorySnapshotResponse:
    """Return all three layers separately (short-term = dialog turns)."""
    owner = _owner_key(client_visitor_id, auth_user)
    short: list[AgentDialogMessageResponse] = []
    working: dict[str, object] = {}
    draft = (client_draft_id or "").strip()
    if draft:
        dialog = await SqlAlchemyAgentDialogRepository(db).get_by_client_draft(
            client_visitor_id=owner, client_draft_id=draft
        )
        if dialog is not None:
            short = [_msg_dto(m) for m in dialog.messages]
            working = dict(dialog.working_memory or {})
    long_term = await SqlAlchemyLongTermMemoryRepository(db).get(owner)
    return AgentMemorySnapshotResponse(
        short_term=short,
        working=working,
        long_term=long_term.to_dict(),
    )


@router.get("/memory/purpose")
async def memory_layer_purpose() -> dict[str, str]:
    return {layer.value: text for layer, text in LAYER_PURPOSE.items()}


@router.post("/memory/write", response_model=AgentMemoryWriteResponse)
async def write_memory_layer(
    payload: AgentMemoryWriteRequest,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    auth_user: OptionalAuthUser,
) -> AgentMemoryWriteResponse:
    """Explicit write into working or long_term — never auto-routes.

    Accepts structured fields or chat_text (slash / Russian directives).
    Creates an empty dialog stub when the first working write arrives.
    """
    from datetime import UTC, datetime
    from uuid import uuid4

    owner = _owner_key(client_visitor_id, auth_user)
    chat = (payload.chat_text or "").strip()
    write: MemoryWrite | None = None
    if chat:
        write = parse_memory_chat_command(chat)
        if write is None:
            raise MessageValidationError(
                "Не распознана команда памяти. Примеры: «запомни цель: …», "
                "«меня зовут …», «/mem working goal …»."
            )
    else:
        layer_raw = (payload.layer or "").strip().lower()
        kind_raw = (payload.kind or "").strip()
        if not layer_raw or not kind_raw:
            raise MessageValidationError("Нужны layer+kind+value или chat_text.")
        try:
            layer = MemoryLayer(layer_raw)
        except ValueError as exc:
            raise MessageValidationError("layer must be working or long_term") from exc
        if layer == MemoryLayer.SHORT_TERM:
            raise MessageValidationError(
                "Краткосрочная память пишется только репликами диалога (run/persist)."
            )
        write = MemoryWrite(
            layer=layer,
            kind=kind_raw,
            key=payload.key,
            value=payload.value,
        )

    draft = (payload.client_draft_id or "").strip()
    dialogs = SqlAlchemyAgentDialogRepository(db)
    ltm_repo = SqlAlchemyLongTermMemoryRepository(db)

    if write.layer == MemoryLayer.WORKING:
        if not draft:
            raise MessageValidationError("Для рабочей памяти нужен client_draft_id.")
        dialog = await dialogs.get_by_client_draft(client_visitor_id=owner, client_draft_id=draft)
        if dialog is None:
            now = datetime.now(UTC)
            dialog = AgentDialog(
                id=uuid4(),
                client_visitor_id=owner,
                visitor_hash=None,
                client_draft_id=draft,
                name=(payload.dialog_name or "Agent").strip()[:120] or "Agent",
                system_prompt=(payload.dialog_system_prompt or "").strip(),
                preferred_model=AUTO_MODEL,
                temperature=None,
                max_tokens=None,
                messages=[],
                working_memory={},
                created_at=now,
                updated_at=now,
            )
        try:
            updated = apply_working_write(WorkingMemory.from_mapping(dialog.working_memory), write)
        except ValueError as exc:
            raise MessageValidationError(str(exc)) from exc
        dialog.working_memory = updated.to_dict()
        dialog.updated_at = datetime.now(UTC)
        await dialogs.save(dialog)
    else:
        current = await ltm_repo.get(owner)
        try:
            updated_lt = apply_long_term_write(current, write)
        except ValueError as exc:
            raise MessageValidationError(str(exc)) from exc
        await ltm_repo.save(owner, updated_lt)

    await db.commit()
    snap = await get_memory_snapshot(
        db=db,
        client_visitor_id=client_visitor_id,
        auth_user=auth_user,
        client_draft_id=draft or None,
    )
    return AgentMemoryWriteResponse(
        short_term=snap.short_term,
        working=snap.working,
        long_term=snap.long_term,
        applied={
            "layer": write.layer.value,
            "kind": write.kind,
            "key": write.key,
            "value": write.value,
        },
        label=describe_memory_write(write),
    )


@router.post("/task", response_model=AgentTaskEventResponse)
async def apply_task_event_endpoint(
    payload: AgentTaskEventRequest,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    auth_user: OptionalAuthUser,
) -> AgentTaskEventResponse:
    """Apply a validated task FSM event (UI chips)."""
    owner = _owner_key(client_visitor_id, auth_user)
    draft = (payload.client_draft_id or "").strip()
    if not draft:
        raise MessageValidationError("client_draft_id обязателен.")
    dialogs = SqlAlchemyAgentDialogRepository(db)
    dialog = await ensure_dialog_for_task(
        dialogs,
        owner_key=owner,
        client_draft_id=draft,
        dialog_name=payload.dialog_name or "Agent",
        dialog_system_prompt=payload.dialog_system_prompt or "",
    )
    event = TaskEvent(
        name=payload.event.strip().lower(),
        goal=payload.goal,
        step=payload.step,
        expected_action=payload.expected_action,
        resume_brief=payload.resume_brief,
        skip_llm=True,
    )
    dialog, label = await apply_task_event_to_dialog(dialog, event, dialogs=dialogs)
    await db.commit()
    working = dict(dialog.working_memory or {})
    task = working.get("task") if isinstance(working.get("task"), dict) else {}
    return AgentTaskEventResponse(
        working=working,
        task=dict(task) if isinstance(task, dict) else {},
        label=label,
        dialog_id=dialog.id,
    )


@router.post("/invariants", response_model=AgentInvariantEventResponse)
async def apply_invariant_event_endpoint(
    payload: AgentInvariantEventRequest,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
    auth_user: OptionalAuthUser,
) -> AgentInvariantEventResponse:
    """Add / seed / remove invariants (UI chips). Stored apart from chat turns."""
    owner = _owner_key(client_visitor_id, auth_user)
    draft = (payload.client_draft_id or "").strip()
    if not draft:
        raise MessageValidationError("client_draft_id обязателен.")
    dialogs = SqlAlchemyAgentDialogRepository(db)
    dialog = await ensure_dialog_for_invariants(
        dialogs,
        owner_key=owner,
        client_draft_id=draft,
        dialog_name=payload.dialog_name or "Agent",
        dialog_system_prompt=payload.dialog_system_prompt or "",
    )
    event = InvariantEvent(
        name=payload.event.strip().lower(),
        kind=payload.kind,
        statement=payload.statement,
        invariant_id=payload.invariant_id,
        skip_llm=True,
    )
    dialog, label = await apply_invariant_event_to_dialog(dialog, event, dialogs=dialogs)
    await db.commit()
    return AgentInvariantEventResponse(
        invariants=list(dialog.invariants or []),
        label=label,
        dialog_id=dialog.id,
    )


@router.post(
    "/dialogs/{dialog_id}/fork",
    response_model=AgentDialogResponse,
)
async def fork_dialog(
    dialog_id: UUID,
    payload: AgentDialogForkRequest,
    db: DbSession,
    client_visitor_id: ClientVisitorId,
) -> AgentDialogResponse:
    """Checkpoint → new dialog with copied prefix (+ facts/summary)."""
    repo = SqlAlchemyAgentDialogRepository(db)
    source = await repo.get(dialog_id)
    if source is None or source.client_visitor_id != client_visitor_id:
        raise HTTPException(status_code=404, detail="Диалог не найден.")
    child = await fork_agent_dialog(
        dialogs=repo,
        source=source,
        from_message_id=payload.from_message_id,
        client_draft_id=payload.client_draft_id,
        branch_label=payload.label,
    )
    await db.commit()
    return _dialog_dto(child)
