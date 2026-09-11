"""Agent workshop: definition + message → LLM; optional Postgres dialog memory."""

from __future__ import annotations

import logging
import time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.adapters.api.schemas import (
    AgentCompressionResponse,
    AgentContextStrategyResponse,
    AgentDialogForkRequest,
    AgentDialogMessageResponse,
    AgentDialogResponse,
    AgentTokenTruncationResponse,
    AgentTokenUsageResponse,
    AgentWorkshopRunRequest,
    AgentWorkshopRunResponse,
)
from app.adapters.persistence.agent_dialog_repo import SqlAlchemyAgentDialogRepository
from app.application.agent_run import DEFAULT_CONTEXT_LIMIT, run_agent, run_agent_with_dialog
from app.application.dialog_fork import fork_agent_dialog
from app.application.llm_catalog import generation_from_api
from app.core.deps import (
    ClientVisitorId,
    DbSession,
    get_container,
    resolve_visitor_identity,
    spawn_detached,
    visitor_id_header,
)
from app.domain.agent_definition import AgentDefinition
from app.domain.agent_dialog import AgentDialog
from app.domain.analytics import AnalyticsEvent
from app.domain.context_compress import CompressionInfo
from app.domain.context_strategies import StrategyMeta
from app.domain.entities import AUTO_MODEL
from app.domain.errors import MessageValidationError
from app.domain.token_meter import TokenBreakdown

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-workshop", tags=["agent-workshop"])


def _definition_from_payload(payload: AgentWorkshopRunRequest) -> AgentDefinition:
    return AgentDefinition(
        name=(payload.definition.name or "").strip(),
        system_prompt=payload.definition.system_prompt,
        preferred_model=(payload.definition.preferred_model or AUTO_MODEL).strip()
        or AUTO_MODEL,
        temperature=payload.definition.temperature,
        max_tokens=payload.definition.max_tokens,
    )


def _msg_dto(m) -> AgentDialogMessageResponse:
    return AgentDialogMessageResponse(
        id=m.id,
        role=m.role,
        content=m.content,
        model_id=m.model_id,
        created_at=m.created_at.isoformat(),
    )


def _dialog_dto(dialog: AgentDialog) -> AgentDialogResponse:
    return AgentDialogResponse(
        id=dialog.id,
        client_draft_id=dialog.client_draft_id,
        name=dialog.name,
        messages=[_msg_dto(m) for m in dialog.messages],
        updated_at=(dialog.updated_at or dialog.created_at).isoformat()
        if dialog.updated_at or dialog.created_at
        else "",
        summary_text=dialog.summary_text or "",
        summary_until_count=int(dialog.summary_until_count or 0),
        facts=dict(dialog.facts or {}),
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


@router.post("/run", response_model=AgentWorkshopRunResponse)
async def run_workshop_agent(
    payload: AgentWorkshopRunRequest,
    request: Request,
    db: DbSession,
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
    try:
        if payload.persist:
            owner = (client_visitor_id or "").strip().lower()
            if not owner:
                raise MessageValidationError(
                    "Для сохранения диалога нужен заголовок X-Visitor-Id (client id)."
                )
            draft_id = (payload.client_draft_id or "").strip()
            if not draft_id:
                raise MessageValidationError(
                    "Для сохранения диалога передайте client_draft_id."
                )
            identity = resolve_visitor_identity(request, owner)
            vhash = identity[0] if identity else None
            outcome, dialog = await run_agent_with_dialog(
                definition=definition,
                message=payload.message,
                router=container.router,
                dialogs=SqlAlchemyAgentDialogRepository(db),
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
        return AgentWorkshopRunResponse(
            content=content, model_id=model_id, tokens=tokens_out
        )
    except Exception:
        status = "error"
        await db.rollback()
        raise
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)

        async def _emit() -> None:
            try:
                name = (
                    "agent_run_completed" if status == "ok" else "agent_run_failed"
                )
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
) -> AgentDialogResponse:
    """Reload dialog for this browser client id + draft."""
    key = (client_draft_id or "").strip()
    if not key:
        raise MessageValidationError("client_draft_id пуст.")
    dialog = await SqlAlchemyAgentDialogRepository(db).get_by_client_draft(
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
) -> AgentDialogResponse:
    """Wipe stored turns but keep the dialog row (definition stays)."""
    from datetime import UTC, datetime

    key = (client_draft_id or "").strip()
    repo = SqlAlchemyAgentDialogRepository(db)
    dialog = await repo.get_by_client_draft(
        client_visitor_id=client_visitor_id, client_draft_id=key
    )
    if dialog is None:
        raise MessageValidationError("Диалог ещё не создан — нечего очищать.")
    dialog.messages = []
    dialog.summary_text = ""
    dialog.summary_until_count = 0
    dialog.facts = {}
    dialog.updated_at = datetime.now(UTC)
    saved = await repo.save(dialog)
    await db.commit()
    return _dialog_dto(saved)


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
