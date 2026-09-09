from datetime import UTC, datetime
from uuid import uuid4

from app.domain.agent_dialog import AgentDialogMessage
from app.domain.token_meter import (
    build_token_breakdown,
    context_budget,
    estimate_messages_tokens,
    estimate_tokens,
    fit_history_to_budget,
)


def _msg(role: str, content: str) -> AgentDialogMessage:
    return AgentDialogMessage(
        id=str(uuid4()),
        role=role,
        content=content,
        created_at=datetime.now(UTC),
        model_id=None,
    )


def test_estimate_tokens_empty_and_basic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("    ") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_context_budget_reserves_completion() -> None:
    assert context_budget(context_limit=1000, max_tokens=200) == 800
    assert context_budget(context_limit=100, max_tokens=1000) == 75  # reserve capped at limit//4


def test_fit_keeps_short_history() -> None:
    history = [_msg("user", "hi"), _msg("assistant", "hello")]
    kept, trunc = fit_history_to_budget(
        system_prompt="sys",
        history=history,
        user_message="next",
        context_limit=8192,
        max_tokens=512,
    )
    assert kept == history
    assert trunc.applied is False
    assert trunc.dropped_messages == 0


def test_fit_drops_oldest_when_over_budget() -> None:
    # Force tiny budget so oldest blob messages are dropped.
    blob = "x" * 200  # ~50 tok each
    history = [
        _msg("user", blob),
        _msg("assistant", blob),
        _msg("user", "tail-user"),
        _msg("assistant", "tail-asst"),
    ]
    kept, trunc = fit_history_to_budget(
        system_prompt="S",
        history=history,
        user_message="NOW",
        context_limit=80,
        max_tokens=16,
    )
    assert trunc.applied is True
    assert trunc.dropped_messages >= 1
    assert trunc.dropped_tokens_est > 0
    # Fixed system+user always leave room only for a short tail.
    assert all(m.content != blob for m in kept) or len(kept) < len(history)
    assert estimate_tokens("S") + estimate_messages_tokens(kept) + estimate_tokens(
        "NOW"
    ) <= trunc.budget


def test_build_token_breakdown_totals() -> None:
    history = [_msg("user", "abcd"), _msg("assistant", "efgh")]
    trunc = fit_history_to_budget(
        system_prompt="sys!",
        history=history,
        user_message="ask!",
        context_limit=8192,
        max_tokens=100,
    )[1]
    bd = build_token_breakdown(
        system_prompt="sys!",
        history_before=history,
        history_after=history,
        user_message="ask!",
        completion="resp!!!!",
        model_id="google/gemini-2.5-flash",
        truncation=trunc,
    )
    assert bd.history_before == bd.history_after == 2
    assert bd.request == estimate_tokens("sys!") + 2 + estimate_tokens("ask!")
    assert bd.completion == estimate_tokens("resp!!!!")
    assert bd.total == bd.request + bd.completion
    assert bd.cost_proxy == 0.4
