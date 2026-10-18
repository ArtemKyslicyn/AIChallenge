"""Classify corpus sources: live handbook vs historical plans."""

from __future__ import annotations

HANDBOOK = "handbook"
HISTORY = "history"
ALL = "all"

_VALID = frozenset({HANDBOOK, HISTORY, ALL})


def normalize_corpus_tier(raw: str | None) -> str:
    value = (raw or ALL).strip().lower()
    return value if value in _VALID else ALL


def corpus_tier_for_source(source: str) -> str:
    """Plans under docs/superpowers are history; everything else is handbook."""
    path = source.replace("\\", "/").lstrip("./")
    if path.startswith("docs/superpowers/") or "/docs/superpowers/" in path:
        return HISTORY
    if path.startswith("superpowers/"):
        return HISTORY
    return HANDBOOK


def source_matches_tier(source: str, tier: str | None) -> bool:
    wanted = normalize_corpus_tier(tier)
    if wanted == ALL:
        return True
    return corpus_tier_for_source(source) == wanted
