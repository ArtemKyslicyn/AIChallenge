"""Explicit preference signal: what a reader thought of one assistant answer.

Three entities, three readers. ``MessageFeedback`` is the stored vote,
``ModelFeedbackStats`` is the aggregate the router and the Lab both consult,
and ``PreferenceRow`` is the export line handed to whoever trains offline.

Nothing here knows about HTTP or SQL — the vote is a domain fact, and the
threshold that turns votes into a routing penalty lives with the router.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, get_args
from uuid import UUID

from app.domain.tracing import AttemptRecord

#: Deliberately two values, not a score: a five-star scale invites deliberation
#: and collects less signal than a single click either way.
FeedbackValue = Literal["up", "down"]

FEEDBACK_VALUES: frozenset[str] = frozenset(get_args(FeedbackValue))


def parse_feedback_value(raw: str) -> FeedbackValue:
    """Narrow an untrusted string to the two values the domain accepts."""
    if raw == "up":
        return "up"
    if raw == "down":
        return "down"
    raise ValueError(f"unknown feedback value: {raw!r}")


@dataclass(slots=True)
class MessageFeedback:
    """One vote on one assistant message.

    ``session_id`` is denormalized so the export and the stats query never have
    to walk back through ``messages`` just to scope a window, and so a vote
    stays attributable after its message is edited in place by the rescue path.
    """

    id: UUID
    message_id: UUID
    session_id: UUID
    #: Already hashed upstream; ``None`` when the browser sent no visitor id.
    visitor_hash: str | None
    value: FeedbackValue
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ModelFeedbackStats:
    """Up/down counts for one model over a window — computed, never stored."""

    model_id: str
    ups: int
    downs: int

    @property
    def total(self) -> int:
        return self.ups + self.downs

    @property
    def down_rate(self) -> float:
        """Zero votes means zero rate, not an undefined one.

        The caller that cares about confidence checks ``total`` against a
        minimum; folding that into the rate here would hide the distinction
        between "nobody voted" and "everybody liked it".
        """
        n = self.total
        return 0.0 if n == 0 else self.downs / n


@dataclass(frozen=True, slots=True)
class PreferenceRow:
    """One JSONL line of the preference dataset.

    ``prompt`` and ``answer`` stay ``None`` unless the export was explicitly
    asked to include content: the default dump is a routing dataset, not a
    transcript.
    """

    message_id: UUID
    model_id: str | None
    feedback: FeedbackValue
    created_at: datetime
    ttft_ms: int | None = None
    total_ms: int | None = None
    #: Empty when no run trace was recorded for this message — an older answer,
    #: or one produced while RUN_TRACE_ENABLED was off.
    attempts: list[AttemptRecord] = field(default_factory=list)
    prompt: str | None = None
    answer: str | None = None
