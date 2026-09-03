"""Observability entities: what one completion cost, and who was tried for it.

A ``RunTrace`` is written once per assistant turn, after the answer is durable.
It is deliberately free of prompt text: routing decisions are measurable
without storing what anyone typed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.domain.cascade import CASCADE_OFF

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
    # Defaults, so every existing construction site keeps working — and so a
    # turn the cascade never touched cannot be mistaken for a cheap answer.
    # They sit at the end because a dataclass forbids a defaulted field before
    # a required one, and ``status``/``created_at`` have no defaults.
    #: off | cheap | escalated — см. app.domain.cascade
    cascade_stage: str = CASCADE_OFF
    #: Кто отвечал первым. None, когда каскад не участвовал.
    cheap_model_id: str | None = None
    #: Вердикт скорера 0..1. None, когда скорер не вызывался.
    cheap_score: float | None = None
    #: Оценка судьи 0..1. None — не судили или разбор не удался.
    quality_score: float | None = None
    #: Кто судил. Нужен, чтобы агрегаты не смешивали двух разных судей молча.
    quality_model_id: str | None = None


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
    # Defaulted, and therefore last: an aggregate built before the judge
    # existed is one nobody judged, not one that scored zero.
    #: Среднее судейской оценки 0..1 по прогонам, у которых она есть.
    avg_quality: float | None = None
    #: Сколько прогонов окна реально оценены. Без него среднее читается как факт.
    judged_n: int = 0
