"""Sliding window: keep last N messages only."""

from __future__ import annotations

from app.domain.agent_dialog import AgentDialogMessage


def apply_sliding(
    messages: list[AgentDialogMessage],
    *,
    recent_keep: int,
) -> tuple[list[AgentDialogMessage], int, int]:
    keep = max(0, int(recent_keep))
    if keep <= 0 or len(messages) <= keep:
        return list(messages), len(messages), 0
    recent = list(messages[-keep:])
    dropped = len(messages) - len(recent)
    return recent, len(recent), dropped
