"""Rolling history compression: keep recent N, summarize the rest."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.agent_dialog import AgentDialogMessage
from app.domain.token_meter import estimate_messages_tokens, estimate_tokens

DEFAULT_RECENT_KEEP = 6
DEFAULT_SUMMARIZE_EVERY = 10

SUMMARY_PREFIX = "Сводка более раннего диалога:\n"


@dataclass(frozen=True, slots=True)
class CompressionPlan:
    recent: list[AgentDialogMessage]
    to_summarize: list[AgentDialogMessage]
    needs_refresh: bool
    covered_by_summary: int
    recent_kept: int


@dataclass(frozen=True, slots=True)
class CompressionInfo:
    enabled: bool
    summary_used: bool
    summary_refreshed: bool
    summary_text: str
    recent_kept: int
    covered_by_summary: int
    tokens_raw_est: int
    tokens_compressed_est: int


def plan_compression(
    messages: list[AgentDialogMessage],
    *,
    summary_until_count: int,
    recent_keep: int = DEFAULT_RECENT_KEEP,
    summarize_every: int = DEFAULT_SUMMARIZE_EVERY,
) -> CompressionPlan:
    keep = max(0, int(recent_keep))
    every = max(1, int(summarize_every))
    covered = max(0, min(int(summary_until_count), len(messages)))
    if keep <= 0 or len(messages) <= keep:
        return CompressionPlan(
            recent=list(messages),
            to_summarize=[],
            needs_refresh=False,
            covered_by_summary=covered,
            recent_kept=len(messages),
        )
    older_end = len(messages) - keep
    recent = list(messages[older_end:])
    backlog = list(messages[covered:older_end])
    needs_refresh = len(backlog) >= every
    return CompressionPlan(
        recent=recent,
        to_summarize=backlog,
        needs_refresh=needs_refresh,
        covered_by_summary=covered,
        recent_kept=len(recent),
    )


def build_summarizer_prompt(
    *,
    prior_summary: str,
    chunk: list[AgentDialogMessage],
) -> str:
    lines: list[str] = []
    if prior_summary.strip():
        lines.append("Текущая сводка:")
        lines.append(prior_summary.strip())
        lines.append("")
    lines.append("Новые реплики для включения в сводку:")
    for m in chunk:
        role = "Пользователь" if m.role == "user" else "Ассистент"
        lines.append(f"{role}: {m.content.strip()}")
    lines.append("")
    lines.append(
        "Обнови сводку диалога: факты, имена, решения, открытые вопросы. "
        "Кратко, на русском, без преамбулы."
    )
    return "\n".join(lines)


def estimate_raw_request_tokens(
    *,
    system_prompt: str,
    messages: list[AgentDialogMessage],
    user_message: str,
) -> int:
    return (
        estimate_tokens(system_prompt)
        + estimate_messages_tokens(messages)
        + estimate_tokens(user_message)
    )


def estimate_compressed_request_tokens(
    *,
    system_prompt: str,
    summary_text: str,
    recent: list[AgentDialogMessage],
    user_message: str,
) -> int:
    sys = system_prompt.strip()
    if summary_text.strip():
        sys = f"{sys}\n\n---\n{SUMMARY_PREFIX}{summary_text.strip()}"
    return (
        estimate_tokens(sys)
        + estimate_messages_tokens(recent)
        + estimate_tokens(user_message)
    )


def merge_system_with_summary(system_prompt: str, summary_text: str) -> str:
    sys = system_prompt.strip()
    s = (summary_text or "").strip()
    if not s:
        return sys
    return f"{sys}\n\n---\n{SUMMARY_PREFIX}{s}"
