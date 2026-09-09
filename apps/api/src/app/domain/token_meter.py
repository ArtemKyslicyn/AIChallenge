"""Approximate token metering and context-budget fitting for agents."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.agent_dialog import AgentDialogMessage
from app.domain.entities import ChatMessage, MessageRole


def estimate_tokens(text: str | None) -> int:
    """Platform approx: ~4 chars per token (same idea as chat / studio)."""
    if not text:
        return 0
    t = text.strip()
    if not t:
        return 0
    return max(1, len(t) // 4)


def estimate_messages_tokens(messages: list[ChatMessage] | list[AgentDialogMessage]) -> int:
    total = 0
    for m in messages:
        total += estimate_tokens(getattr(m, "content", "") or "")
    return total


def estimate_cost_proxy(model_id: str | None) -> float:
    if not model_id:
        return 1.0
    mid = model_id.lower()
    if ":free" in mid or mid.endswith("/free") or "openrouter/free" in mid:
        return 0.05
    if any(x in mid for x in ("nano", "mini", "flash", "haiku")):
        return 0.4
    if any(x in mid for x in ("235b", "ultra", "opus", "gpt-4", "o1", "o3", "super")):
        return 3.0
    if any(x in mid for x in ("v3.2", "v3", "sonnet", "pro")):
        return 1.6
    return 1.0


@dataclass(frozen=True, slots=True)
class TruncationInfo:
    applied: bool
    dropped_messages: int
    dropped_tokens_est: int
    context_limit: int
    budget: int


@dataclass(frozen=True, slots=True)
class TokenBreakdown:
    request: int
    history_before: int
    history_after: int
    completion: int
    total: int
    cost_proxy: float
    truncation: TruncationInfo


def context_budget(*, context_limit: int, max_tokens: int | None) -> int:
    limit = max(64, int(context_limit))
    reserve = min(int(max_tokens or 512), max(1, limit // 4))
    return max(32, limit - reserve)


def fit_history_to_budget(
    *,
    system_prompt: str,
    history: list[AgentDialogMessage],
    user_message: str,
    context_limit: int,
    max_tokens: int | None,
) -> tuple[list[AgentDialogMessage], TruncationInfo]:
    """Drop oldest history messages until system+history+user fit in budget."""
    budget = context_budget(context_limit=context_limit, max_tokens=max_tokens)
    system_tok = estimate_tokens(system_prompt)
    user_tok = estimate_tokens(user_message)
    fixed = system_tok + user_tok
    before = estimate_messages_tokens(history)

    kept = list(history)
    dropped = 0
    while kept and fixed + estimate_messages_tokens(kept) > budget:
        kept.pop(0)
        dropped += 1

    after = estimate_messages_tokens(kept)
    return kept, TruncationInfo(
        applied=dropped > 0,
        dropped_messages=dropped,
        dropped_tokens_est=max(0, before - after),
        context_limit=max(64, int(context_limit)),
        budget=budget,
    )


def build_token_breakdown(
    *,
    system_prompt: str,
    history_before: list[AgentDialogMessage],
    history_after: list[AgentDialogMessage],
    user_message: str,
    completion: str,
    model_id: str | None,
    truncation: TruncationInfo,
) -> TokenBreakdown:
    request = (
        estimate_tokens(system_prompt)
        + estimate_messages_tokens(history_after)
        + estimate_tokens(user_message)
    )
    completion_tok = estimate_tokens(completion)
    return TokenBreakdown(
        request=request,
        history_before=estimate_messages_tokens(history_before),
        history_after=estimate_messages_tokens(history_after),
        completion=completion_tok,
        total=request + completion_tok,
        cost_proxy=estimate_cost_proxy(model_id),
        truncation=truncation,
    )


def history_to_chat_turns(history: list[AgentDialogMessage]) -> list[ChatMessage]:
    turns: list[ChatMessage] = []
    for prior in history:
        if prior.role == "user":
            turns.append(ChatMessage(role=MessageRole.USER, content=prior.content))
        elif prior.role == "assistant":
            turns.append(ChatMessage(role=MessageRole.ASSISTANT, content=prior.content))
    return turns
