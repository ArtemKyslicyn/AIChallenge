"""Unit tests for context strategy assembly."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.agent_dialog import AgentDialogMessage
from app.domain.context_strategies import (
    ContextMode,
    ContextState,
    assemble_context,
    resolve_context_mode,
)
from app.domain.context_strategies.facts import merge_facts, parse_facts_json
from app.domain.errors import MessageValidationError


def _msgs(n: int) -> list[AgentDialogMessage]:
    now = datetime.now(UTC)
    out: list[AgentDialogMessage] = []
    for i in range(n):
        out.append(
            AgentDialogMessage(
                id=str(i),
                role="user" if i % 2 == 0 else "assistant",
                content=f"m{i} " + ("x" * 20),
                created_at=now,
                model_id="fake" if i % 2 else None,
            )
        )
    return out


def test_resolve_mode_none_default() -> None:
    assert resolve_context_mode(context_mode=None, compress=None) == ContextMode.NONE
    assert resolve_context_mode(context_mode=None, compress=False) == ContextMode.NONE


def test_resolve_mode_compress_compat() -> None:
    assert resolve_context_mode(context_mode=None, compress=True) == ContextMode.COMPRESS


def test_resolve_mode_conflict() -> None:
    with pytest.raises(MessageValidationError):
        resolve_context_mode(context_mode="sliding", compress=True)


def test_sliding_drops_older() -> None:
    msgs = _msgs(12)
    result = assemble_context(
        msgs,
        mode=ContextMode.SLIDING,
        state=ContextState(),
        system_prompt="sys",
        user_message="hi",
        recent_keep=4,
    )
    assert len(result.history) == 4
    assert result.meta.dropped == 8
    assert result.meta.tokens_strategy_est < result.meta.tokens_raw_est
    assert result.system_extra == ""


def test_facts_injects_block() -> None:
    msgs = _msgs(10)
    state = ContextState(facts={"goal": "ТЗ для чата", "stack": "Python"})
    result = assemble_context(
        msgs,
        mode=ContextMode.FACTS,
        state=state,
        system_prompt="sys",
        user_message="продолжи",
        recent_keep=4,
        facts_updated=True,
    )
    assert "goal" in result.system_extra
    assert "ТЗ для чата" in result.system_extra
    assert len(result.history) == 4
    assert result.meta.facts_updated is True


def test_none_keeps_all() -> None:
    msgs = _msgs(10)
    result = assemble_context(
        msgs,
        mode=ContextMode.NONE,
        state=ContextState(),
        system_prompt="sys",
        user_message="hi",
    )
    assert len(result.history) == 10
    assert result.system_extra == ""


def test_merge_and_parse_facts() -> None:
    merged = merge_facts({"a": "1", "b": "2"}, {"b": "", "c": "3"})
    assert merged == {"a": "1", "c": "3"}
    parsed = parse_facts_json('{"goal": "demo", "x": ""}')
    assert parsed == {"goal": "demo", "x": ""}


def test_compress_signals_refresh() -> None:
    msgs = _msgs(20)
    result = assemble_context(
        msgs,
        mode=ContextMode.COMPRESS,
        state=ContextState(summary_text="", summary_until_count=0),
        system_prompt="sys",
        user_message="hi",
        recent_keep=4,
        summarize_every=6,
    )
    assert result.needs_summary_refresh is True
    assert len(result.summary_chunk) >= 6
