"""Pluggable context assembly strategies (Day 10)."""

from __future__ import annotations

from app.domain.context_strategies.assemble import assemble_context, resolve_context_mode
from app.domain.context_strategies.types import (
    DEFAULT_FACTS_RECENT_KEEP,
    AssemblyResult,
    ContextMode,
    ContextState,
    StrategyMeta,
)

__all__ = [
    "DEFAULT_FACTS_RECENT_KEEP",
    "AssemblyResult",
    "ContextMode",
    "ContextState",
    "StrategyMeta",
    "assemble_context",
    "resolve_context_mode",
]
