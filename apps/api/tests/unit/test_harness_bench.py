"""Unit tests for harness-bench scoring and leaderboard matching."""

from __future__ import annotations

from app.domain.harness_bench import (
    build_leaderboard,
    compute_pass_metrics,
    match_board_row,
    parse_board,
    pass_at_k,
    pass_hat_k,
    score_pct,
)


def _sample_board():
    return parse_board(
        {
            "task_set": "v0.16.0",
            "total_tasks": 391,
            "source_url": "https://example.test",
            "landing_url": "https://example.test/landing",
            "updated_at": "2026-09-13T00:00:00Z",
            "rows": [
                {
                    "harness": "Pi",
                    "profile": None,
                    "model_label": "DeepSeek V4 Flash 0731 (high)",
                    "passed": 387,
                    "total": 391,
                    "pct": 99.0,
                    "steps": 1694,
                    "tokens": 1000,
                },
                {
                    "harness": "deepagents",
                    "profile": "none",
                    "model_label": "DeepSeek V4 Flash",
                    "passed": 320,
                    "total": 391,
                    "pct": 81.8,
                    "steps": 5048,
                    "tokens": 2000,
                },
                {
                    "harness": "deepagents",
                    "profile": "none",
                    "model_label": "Qwen3 Coder 30B-A3B",
                    "passed": 284,
                    "total": 391,
                    "pct": 72.6,
                    "steps": 100,
                    "tokens": 1,
                },
            ],
        }
    )


def test_score_pct() -> None:
    assert score_pct(320, 391) == 81.8


def test_pass_metrics_ported() -> None:
    assert pass_at_k(5, 3, 1) == 0.6
    assert pass_hat_k(5, 3, 2) > 0
    metrics = compute_pass_metrics(
        [("t1", True), ("t1", False), ("t2", True), ("t2", True)],
        pass_at_ks=(1,),
        pass_hat_ks=(2,),
    )
    assert [m.label for m in metrics] == ["pass@1", "pass^2"]


def test_match_prefers_highest_passed() -> None:
    board = _sample_board()
    row = match_board_row("deepseek/deepseek-v4-flash", board)
    assert row is not None
    assert row.passed == 387


def test_leaderboard_ranks_connected_only() -> None:
    board = _sample_board()
    entries = build_leaderboard(
        [
            "deepseek/deepseek-v4-flash",
            "qwen/qwen3-coder-30b",
            "google/gemini-2.5-flash",
        ],
        board,
    )
    matched = [e for e in entries if e.matched]
    unmatched = [e for e in entries if not e.matched]
    assert matched[0].rank == 1
    assert matched[0].model_id == "deepseek/deepseek-v4-flash"
    assert matched[0].passed == 387
    assert matched[1].model_id.startswith("qwen/")
    assert unmatched[0].model_id == "google/gemini-2.5-flash"
    assert unmatched[0].rank is None
