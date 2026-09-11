from datetime import UTC, datetime
from uuid import uuid4

from app.domain.agent_dialog import AgentDialogMessage
from app.domain.context_compress import (
    build_summarizer_prompt,
    estimate_compressed_request_tokens,
    estimate_raw_request_tokens,
    plan_compression,
)


def _msg(role: str, content: str) -> AgentDialogMessage:
    return AgentDialogMessage(
        id=str(uuid4()),
        role=role,
        content=content,
        created_at=datetime.now(UTC),
    )


def test_plan_keeps_all_when_short() -> None:
    msgs = [_msg("user", "a"), _msg("assistant", "b")]
    plan = plan_compression(msgs, summary_until_count=0, recent_keep=6, summarize_every=10)
    assert plan.recent == msgs
    assert plan.to_summarize == []
    assert plan.needs_refresh is False


def test_plan_splits_and_needs_refresh() -> None:
    msgs = [_msg("user", f"u{i}") for i in range(16)]
    # 16 messages, keep 6 → older=10; covered=0 → backlog=10 ≥ every=10
    plan = plan_compression(msgs, summary_until_count=0, recent_keep=6, summarize_every=10)
    assert len(plan.recent) == 6
    assert len(plan.to_summarize) == 10
    assert plan.needs_refresh is True


def test_plan_no_refresh_when_already_covered() -> None:
    msgs = [_msg("user", f"u{i}") for i in range(16)]
    plan = plan_compression(msgs, summary_until_count=10, recent_keep=6, summarize_every=10)
    assert len(plan.recent) == 6
    assert plan.to_summarize == []
    assert plan.needs_refresh is False


def test_summarizer_prompt_includes_prior_and_chunk() -> None:
    chunk = [_msg("user", "Меня зовут Артем"), _msg("assistant", "Приятно")]
    text = build_summarizer_prompt(prior_summary="Уже знаем Python.", chunk=chunk)
    assert "Уже знаем Python" in text
    assert "Артем" in text


def test_token_estimates_compressed_smaller() -> None:
    fat = "x" * 400
    msgs = [_msg("user", fat), _msg("assistant", fat)] * 5
    raw = estimate_raw_request_tokens(
        system_prompt="sys", messages=msgs, user_message="q"
    )
    compressed = estimate_compressed_request_tokens(
        system_prompt="sys",
        summary_text="краткая сводка",
        recent=msgs[-2:],
        user_message="q",
    )
    assert compressed < raw
