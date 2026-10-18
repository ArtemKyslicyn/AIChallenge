"""Handbook vs history corpus classification."""

from aichallenge_rag.corpus_tier import (
    ALL,
    HANDBOOK,
    HISTORY,
    corpus_tier_for_source,
    normalize_corpus_tier,
    source_matches_tier,
)


def test_superpowers_is_history() -> None:
    assert corpus_tier_for_source("docs/superpowers/plans/x.md") == HISTORY
    assert corpus_tier_for_source("docs/superpowers/specs/y.md") == HISTORY


def test_live_docs_are_handbook() -> None:
    assert corpus_tier_for_source("docs/project-structure.md") == HANDBOOK
    assert corpus_tier_for_source("docs/stand-edge-ports.md") == HANDBOOK
    assert corpus_tier_for_source("AGENTS.md") == HANDBOOK
    assert corpus_tier_for_source("README.md") == HANDBOOK


def test_filter_handbook_excludes_plans() -> None:
    assert source_matches_tier("docs/project-structure.md", HANDBOOK)
    assert not source_matches_tier("docs/superpowers/plans/x.md", HANDBOOK)
    assert source_matches_tier("docs/superpowers/plans/x.md", HISTORY)
    assert source_matches_tier("docs/superpowers/plans/x.md", ALL)


def test_normalize_unknown_defaults_to_all() -> None:
    assert normalize_corpus_tier(None) == ALL
    assert normalize_corpus_tier("weird") == ALL
    assert normalize_corpus_tier("Handbook") == HANDBOOK
