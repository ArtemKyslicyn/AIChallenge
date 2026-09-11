"""Types for modular context strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from app.domain.agent_dialog import AgentDialogMessage

DEFAULT_FACTS_RECENT_KEEP = 8


class ContextMode(StrEnum):
    NONE = "none"
    COMPRESS = "compress"
    SLIDING = "sliding"
    FACTS = "facts"


@dataclass(slots=True)
class ContextState:
    summary_text: str = ""
    summary_until_count: int = 0
    facts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StrategyMeta:
    mode: ContextMode
    recent_kept: int = 0
    dropped: int = 0
    facts: dict[str, str] = field(default_factory=dict)
    facts_updated: bool = False
    summary_used: bool = False
    summary_refreshed: bool = False
    tokens_raw_est: int = 0
    tokens_strategy_est: int = 0
    # Compress-compat fields for Day-9 UI
    covered_by_summary: int = 0
    summary_text: str = ""


@dataclass(frozen=True, slots=True)
class AssemblyResult:
    history: list[AgentDialogMessage]
    system_extra: str
    state: ContextState
    meta: StrategyMeta
    #: When compress needs an LLM refresh before assembly completes.
    needs_summary_refresh: bool = False
    summary_chunk: tuple[AgentDialogMessage, ...] = ()
