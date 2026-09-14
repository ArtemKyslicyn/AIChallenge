"""Harness-bench-fast scoring helpers and leaderboard matching.

Upstream: https://github.com/ai-forever/harness-bench-fast
Primary board metric (README): Result = passed/total, % = passed/total*100.
``pass@k`` / ``pass^k`` are ported from ``harness_bench.metrics`` for multi-attempt runs.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from math import comb
from typing import Any, Literal

MetricKind = Literal["pass@", "pass^"]


@dataclass(frozen=True, slots=True)
class BoardRow:
    harness: str
    profile: str | None
    model_label: str
    passed: int
    total: int
    pct: float
    steps: int | None = None
    tokens: int | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class HarnessBoard:
    task_set: str
    total_tasks: int
    source_url: str
    landing_url: str
    updated_at: str
    rows: tuple[BoardRow, ...]


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    rank: int | None
    model_id: str
    model_label: str
    harness: str | None
    profile: str | None
    passed: int | None
    total: int | None
    pct: float | None
    steps: int | None
    tokens: int | None
    in_chain: bool
    matched: bool


@dataclass(frozen=True, slots=True)
class PassMetric:
    kind: MetricKind
    k: int
    value: float
    task_count: int

    @property
    def label(self) -> str:
        return f"{self.kind}{self.k}"


def score_pct(passed: int, total: int) -> float:
    """README-style percentage for a single full run."""
    if total <= 0:
        raise ValueError("total must be positive")
    if passed < 0 or passed > total:
        raise ValueError("passed must be between 0 and total")
    return round(100.0 * passed / total, 1)


def pass_at_k(num_samples: int, num_correct: int, k: int) -> float:
    """Estimate P(at least one of k samples passes). Ported from harness-bench."""
    _validate_counts(num_samples, num_correct, k)
    if num_correct == 0:
        return 0.0
    if num_samples - num_correct < k:
        return 1.0
    return 1.0 - (comb(num_samples - num_correct, k) / comb(num_samples, k))


def pass_hat_k(num_samples: int, num_correct: int, k: int) -> float:
    """Estimate P(all k samples pass). Ported from harness-bench."""
    _validate_counts(num_samples, num_correct, k)
    if num_correct < k:
        return 0.0
    return comb(num_correct, k) / comb(num_samples, k)


def compute_pass_metrics(
    results: Iterable[tuple[str, bool]],
    *,
    pass_at_ks: Sequence[int] = (),
    pass_hat_ks: Sequence[int] = (),
) -> list[PassMetric]:
    grouped: OrderedDict[str, list[bool]] = OrderedDict()
    for task_id, passed in results:
        grouped.setdefault(task_id, []).append(passed)
    metrics: list[PassMetric] = []
    for k in _dedupe_positive(pass_at_ks):
        metrics.append(_group_metric(grouped, "pass@", k))
    for k in _dedupe_positive(pass_hat_ks):
        metrics.append(_group_metric(grouped, "pass^", k))
    return metrics


def parse_board(raw: Mapping[str, Any]) -> HarnessBoard:
    rows_raw = raw.get("rows")
    if not isinstance(rows_raw, list) or not rows_raw:
        raise ValueError("harness board requires non-empty rows")
    rows: list[BoardRow] = []
    for item in rows_raw:
        if not isinstance(item, Mapping):
            continue
        passed = int(item["passed"])
        total = int(item["total"])
        pct = float(item["pct"]) if item.get("pct") is not None else score_pct(passed, total)
        profile = item.get("profile")
        rows.append(
            BoardRow(
                harness=str(item.get("harness") or ""),
                profile=None if profile in (None, "", "—", "-") else str(profile),
                model_label=str(item.get("model_label") or ""),
                passed=passed,
                total=total,
                pct=pct,
                steps=_opt_int(item.get("steps")),
                tokens=_opt_int(item.get("tokens")),
                source=str(item["source"]) if item.get("source") else None,
            )
        )
    if not rows:
        raise ValueError("no valid harness board rows")
    return HarnessBoard(
        task_set=str(raw.get("task_set") or "unknown"),
        total_tasks=int(raw.get("total_tasks") or rows[0].total),
        source_url=str(raw.get("source_url") or ""),
        landing_url=str(raw.get("landing_url") or ""),
        updated_at=str(raw.get("updated_at") or ""),
        rows=tuple(rows),
    )


#: Provider slug fragments → board label needle. Longest token wins; no cross-family aliases.
#: Only map ids that really are that board model (not "same vendor, different release").
_ALIAS_NEEDLES: tuple[tuple[str, str], ...] = tuple(
    sorted(
        (
            ("deepseek-v4-flash", "deepseek v4 flash"),
            ("deepseek-v4", "deepseek v4 flash"),
            ("kimi-k3", "kimi k3"),
            ("kimi/k3", "kimi k3"),
            ("claude-haiku-4.5", "claude haiku 4.5"),
            ("claude-haiku", "claude haiku"),
            ("glm-5.2", "glm-5.2"),
            ("qwen3-coder-30b", "qwen3 coder"),
            ("qwen3-coder", "qwen3 coder"),
            ("gpt-oss-120b", "gpt-oss-120b"),
            ("gpt-oss-20b", "gpt-oss-20b"),
            ("gigachat-3-ultra", "gigachat 3 ultra"),
            ("gigachat-3.5", "gigachat 3.5"),
            ("gigachat-3-pro", "gigachat 3 pro"),
            ("gigachat-3-lightning", "gigachat 3 lightning"),
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
)

#: Family/vendor tokens that must not alone decide a match.
_WEAK_TOKENS = frozenset(
    {
        "deepseek",
        "qwen",
        "qwen3",
        "claude",
        "google",
        "gemini",
        "openai",
        "gpt",
        "kimi",
        "glm",
        "gigachat",
        "mistral",
        "llama",
        "nvidia",
        "meta",
        "coder",
        "chat",
        "instruct",
        "flash",
        "pro",
        "ultra",
        "lite",
        "mini",
        "nano",
        "free",
        "openrouter",
    }
)


def normalize_label(text: str) -> str:
    return " ".join(text.lower().replace("_", " ").replace("/", " ").replace(":", " ").split())


def match_board_row(model_id: str, board: HarnessBoard) -> BoardRow | None:
    """Pick the best README row for a connected model id (highest passed, then fewer steps)."""
    needle = _needle_for_model(model_id)
    if not needle:
        needle = normalize_label(model_id.split("/")[-1].split(":")[0])
    tokens = [tok for tok in needle.split() if len(tok) > 2]
    if not tokens:
        return None
    strong = [tok for tok in tokens if tok not in _WEAK_TOKENS]
    # A single vendor token ("deepseek") must not match any board row by itself.
    if not strong and len(tokens) < 2:
        return None

    candidates: list[BoardRow] = []
    for row in board.rows:
        label = normalize_label(row.model_label)
        if needle in label:
            candidates.append(row)
            continue
        # Token match: every significant token + at least one non-vendor cue.
        if strong and all(tok in label for tok in tokens):
            candidates.append(row)
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda r: (-r.passed, r.steps if r.steps is not None else 10**12, r.model_label),
    )[0]


def build_leaderboard(
    connected_model_ids: Sequence[str],
    board: HarnessBoard,
) -> list[LeaderboardEntry]:
    """Rank connected models that have a harness match; append unmatched at the end."""
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for mid in connected_model_ids:
        mid = (mid or "").strip()
        if not mid or mid in seen:
            continue
        seen.add(mid)
        ordered_ids.append(mid)

    scored: list[tuple[str, BoardRow]] = []
    unmatched: list[str] = []
    for mid in ordered_ids:
        row = match_board_row(mid, board)
        if row is None:
            unmatched.append(mid)
        else:
            scored.append((mid, row))

    scored.sort(
        key=lambda pair: (
            -pair[1].passed,
            pair[1].steps if pair[1].steps is not None else 10**12,
            pair[0],
        )
    )

    entries: list[LeaderboardEntry] = []
    for idx, (mid, row) in enumerate(scored, start=1):
        entries.append(
            LeaderboardEntry(
                rank=idx,
                model_id=mid,
                model_label=row.model_label,
                harness=row.harness,
                profile=row.profile,
                passed=row.passed,
                total=row.total,
                pct=row.pct,
                steps=row.steps,
                tokens=row.tokens,
                in_chain=True,
                matched=True,
            )
        )
    for mid in unmatched:
        entries.append(
            LeaderboardEntry(
                rank=None,
                model_id=mid,
                model_label=mid.split("/")[-1],
                harness=None,
                profile=None,
                passed=None,
                total=None,
                pct=None,
                steps=None,
                tokens=None,
                in_chain=True,
                matched=False,
            )
        )
    return entries


def _needle_for_model(model_id: str) -> str | None:
    low = model_id.lower()
    for token, needle in _ALIAS_NEEDLES:
        if _slug_has_token(low, token):
            return needle
    return None


def _slug_has_token(model_id: str, token: str) -> bool:
    """True when ``token`` appears as a slug fragment (not a prefix of a longer id)."""
    if token not in model_id:
        return False
    start = 0
    while True:
        idx = model_id.find(token, start)
        if idx < 0:
            return False
        before = model_id[idx - 1] if idx > 0 else ""
        after_idx = idx + len(token)
        after = model_id[after_idx] if after_idx < len(model_id) else ""
        if (not before or not before.isalnum()) and (not after or not after.isalnum()):
            return True
        start = idx + 1


def _opt_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _group_metric(
    grouped: OrderedDict[str, list[bool]],
    kind: MetricKind,
    k: int,
) -> PassMetric:
    values: list[float] = []
    for task_id, passes in grouped.items():
        num_samples = len(passes)
        num_correct = sum(passes)
        if k > num_samples:
            raise ValueError(
                f"{kind}{k} requires at least {k} attempts for {task_id}; got {num_samples}"
            )
        if kind == "pass@":
            values.append(pass_at_k(num_samples, num_correct, k))
        else:
            values.append(pass_hat_k(num_samples, num_correct, k))
    value = sum(values) / len(values) if values else 0.0
    return PassMetric(kind=kind, k=k, value=value, task_count=len(values))


def _dedupe_positive(values: Sequence[int]) -> tuple[int, ...]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        if value < 1:
            raise ValueError("metric k must be positive")
        if value not in seen:
            out.append(value)
            seen.add(value)
    return tuple(out)


def _validate_counts(num_samples: int, num_correct: int, k: int) -> None:
    if num_samples < 1:
        raise ValueError("num_samples must be positive")
    if k < 1:
        raise ValueError("k must be positive")
    if k > num_samples:
        raise ValueError("k cannot exceed num_samples")
    if num_correct < 0 or num_correct > num_samples:
        raise ValueError("num_correct must be between 0 and num_samples")
