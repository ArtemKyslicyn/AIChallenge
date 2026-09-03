"""Observability entities: what one completion cost, and who was tried for it.

A ``RunTrace`` is written once per assistant turn, after the answer is durable.
It is deliberately free of prompt text: routing decisions are measurable
without storing what anyone typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

#: Terminal states of one turn, mirroring the four ways the chat use case ends.
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_ABORTED = "aborted"
STATUS_EXHAUSTED = "exhausted"

RUN_TRACE_STATUSES = frozenset({STATUS_OK, STATUS_ERROR, STATUS_ABORTED, STATUS_EXHAUSTED})


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """One model the router actually called while serving a single request.

    Frozen on purpose: the journal is an append-only account of what happened,
    so a later stage cannot quietly rewrite an earlier attempt.
    """

    model_id: str
    ok: bool
    reason: str = ""
    #: Time to the first token of *this* attempt, set only when one arrived.
    ttft_ms: int | None = None
    #: Coarse provider label (``quota``, ``timeout``, …) when the attempt failed.
    error_kind: str | None = None


@dataclass(slots=True)
class RunTrace:
    """Everything measurable about one assistant turn."""

    id: UUID
    session_id: UUID
    message_id: UUID
    #: Copied from the session — already hashed, never raw identity.
    visitor_hash: str | None
    preferred_model: str
    resolved_model_id: str | None
    attempts: list[AttemptRecord]
    ttft_ms: int | None
    total_ms: int | None
    token_count_est: int | None
    cost_proxy: float | None
    tool_rounds: int
    tool_ok: bool | None
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ModelAggregate:
    """Read model over a time window — computed, never stored.

    Percentiles and cost are nullable because a window can hold runs that never
    produced a token, and because an unconfigured model has no cost proxy at
    all. ``None`` must stay ``None``: substituting 1.0 would invent a ranking.
    """

    model_id: str
    n: int
    success_rate: float
    p50_ttft_ms: float | None
    p50_total_ms: float | None
    avg_cost_proxy: float | None
    score: float
