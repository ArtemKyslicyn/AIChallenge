"""Assemble LLM history + system_extra for a context mode."""

from __future__ import annotations

from app.domain.agent_dialog import AgentDialogMessage
from app.domain.context_compress import (
    DEFAULT_RECENT_KEEP,
    DEFAULT_SUMMARIZE_EVERY,
    SUMMARY_PREFIX,
    estimate_compressed_request_tokens,
    estimate_raw_request_tokens,
    plan_compression,
)
from app.domain.context_strategies.facts import format_facts_block
from app.domain.context_strategies.sliding import apply_sliding
from app.domain.context_strategies.types import (
    DEFAULT_FACTS_RECENT_KEEP,
    AssemblyResult,
    ContextMode,
    ContextState,
    StrategyMeta,
)
from app.domain.errors import MessageValidationError
from app.domain.token_meter import estimate_messages_tokens, estimate_tokens


def resolve_context_mode(
    *,
    context_mode: str | None,
    compress: bool | None = None,
) -> ContextMode:
    """Resolve mutually exclusive mode; compat compress:true → compress."""
    raw = (context_mode or "").strip().lower() or None
    if raw is not None:
        try:
            mode = ContextMode(raw)
        except ValueError as exc:
            raise MessageValidationError(
                f"Неизвестный context_mode: {context_mode!r}"
            ) from exc
        if compress is True and mode != ContextMode.COMPRESS:
            raise MessageValidationError(
                "compress=true конфликтует с context_mode "
                f"(ожидался compress, получен {mode.value})."
            )
        return mode
    if compress is True:
        return ContextMode.COMPRESS
    return ContextMode.NONE


def _strategy_est(system_prompt: str, system_extra: str, recent: list, user: str) -> int:
    sys = system_prompt.strip()
    extra = (system_extra or "").strip()
    if extra:
        sys = f"{sys}\n\n---\n{extra}"
    return estimate_tokens(sys) + estimate_messages_tokens(recent) + estimate_tokens(user)


def assemble_context(
    messages: list[AgentDialogMessage],
    *,
    mode: ContextMode,
    state: ContextState,
    system_prompt: str,
    user_message: str,
    recent_keep: int | None = None,
    summarize_every: int | None = None,
    facts_updated: bool = False,
) -> AssemblyResult:
    """Pure assembly (no LLM). Compress refresh signaled via needs_summary_refresh."""
    hist = list(messages)
    st = ContextState(
        summary_text=state.summary_text or "",
        summary_until_count=int(state.summary_until_count or 0),
        facts=dict(state.facts or {}),
    )
    sys = system_prompt.strip()
    user = user_message.strip()
    raw_est = estimate_raw_request_tokens(
        system_prompt=sys, messages=hist, user_message=user
    )

    if mode == ContextMode.NONE:
        meta = StrategyMeta(
            mode=mode,
            recent_kept=len(hist),
            dropped=0,
            facts=dict(st.facts),
            tokens_raw_est=raw_est,
            tokens_strategy_est=raw_est,
        )
        return AssemblyResult(history=hist, system_extra="", state=st, meta=meta)

    if mode == ContextMode.SLIDING:
        keep = (
            DEFAULT_FACTS_RECENT_KEEP
            if recent_keep is None
            else max(2, min(40, int(recent_keep)))
        )
        recent, kept, dropped = apply_sliding(hist, recent_keep=keep)
        meta = StrategyMeta(
            mode=mode,
            recent_kept=kept,
            dropped=dropped,
            facts=dict(st.facts),
            tokens_raw_est=raw_est,
            tokens_strategy_est=_strategy_est(sys, "", recent, user),
        )
        return AssemblyResult(history=recent, system_extra="", state=st, meta=meta)

    if mode == ContextMode.FACTS:
        keep = (
            DEFAULT_FACTS_RECENT_KEEP
            if recent_keep is None
            else max(2, min(40, int(recent_keep)))
        )
        recent, kept, dropped = apply_sliding(hist, recent_keep=keep)
        extra = format_facts_block(st.facts)
        meta = StrategyMeta(
            mode=mode,
            recent_kept=kept,
            dropped=dropped,
            facts=dict(st.facts),
            facts_updated=facts_updated,
            tokens_raw_est=raw_est,
            tokens_strategy_est=_strategy_est(sys, extra, recent, user),
        )
        return AssemblyResult(history=recent, system_extra=extra, state=st, meta=meta)

    # compress
    keep = DEFAULT_RECENT_KEEP if recent_keep is None else max(0, min(40, int(recent_keep)))
    every = (
        DEFAULT_SUMMARIZE_EVERY
        if summarize_every is None
        else max(2, min(100, int(summarize_every)))
    )
    plan = plan_compression(
        hist,
        summary_until_count=st.summary_until_count,
        recent_keep=keep,
        summarize_every=every,
    )
    needs_refresh = bool(plan.needs_refresh and plan.to_summarize)
    summary = st.summary_text or ""
    extra = f"{SUMMARY_PREFIX}{summary.strip()}" if summary.strip() else ""
    strategy_est = estimate_compressed_request_tokens(
        system_prompt=sys,
        summary_text=summary,
        recent=plan.recent,
        user_message=user,
    )
    meta = StrategyMeta(
        mode=mode,
        recent_kept=len(plan.recent),
        dropped=max(0, len(hist) - len(plan.recent)),
        facts=dict(st.facts),
        summary_used=bool(summary.strip()),
        summary_refreshed=False,
        tokens_raw_est=raw_est,
        tokens_strategy_est=strategy_est,
        covered_by_summary=st.summary_until_count,
        summary_text=summary,
    )
    return AssemblyResult(
        history=list(plan.recent),
        system_extra=extra,
        state=st,
        meta=meta,
        needs_summary_refresh=needs_refresh,
        summary_chunk=tuple(plan.to_summarize),
    )
