"""Turn thumbs into a routing bias.

Two pieces with deliberately different shapes. ``should_penalize`` is pure
arithmetic over one model's counts, so the same rule can be asserted in a
table test and shown in the Lab. ``FeedbackPenaltyCache`` is the part with a
clock: the router asks it a synchronous question on every request, so the
answer has to already be in memory — reading the database inside candidate
selection would put a query on the path of every single message.

What a penalty *does* lives in :mod:`app.adapters.llm.router`: a penalized
model moves to the end of the chain, it is never dropped. A model having a bad
day must not be able to leave a chat with no chain at all.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.domain.feedback import ModelFeedbackStats
from app.domain.ports import FeedbackRepository

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def should_penalize(
    stats: ModelFeedbackStats, *, min_votes: int, down_rate_threshold: float
) -> bool:
    """Is this model's down-vote rate bad enough, and backed by enough votes?

    The vote floor comes first for a reason: one angry reader on a model's
    first answer is a 100% down rate, and demoting a model on that is noise
    amplification, not feedback.
    """
    if stats.total < min_votes:
        return False
    return stats.down_rate >= down_rate_threshold


class FeedbackPenaltyCache:
    """The set of currently penalized models, refreshed on a timer.

    Two different durations are at play and they are easy to confuse:

    ``window_seconds`` is how far back votes are counted — it is what makes a
    penalty expire, because a bad day drops out of the window on its own.
    ``refresh_seconds`` is only how stale this process's copy may get.
    """

    def __init__(
        self,
        *,
        min_votes: int,
        down_rate_threshold: float,
        window_seconds: int,
        refresh_seconds: int,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._min_votes = min_votes
        self._threshold = down_rate_threshold
        self._window = timedelta(seconds=max(0, window_seconds))
        self._refresh_every = timedelta(seconds=max(0, refresh_seconds))
        self._now = now
        self._penalized: frozenset[str] = frozenset()
        self._fresh_until: datetime | None = None

    @property
    def penalized(self) -> frozenset[str]:
        """The current set, for callers that want to report it rather than ask."""
        return self._penalized

    def is_penalized(self, model_id: str) -> bool:
        """Synchronous by contract — the router calls this per request."""
        return model_id in self._penalized

    async def refresh(self, repo: FeedbackRepository) -> None:
        """Recompute the set, or do nothing while the current one is fresh.

        The freshness deadline is moved *before* the read, not after. Under
        load, many requests arrive within the same interval; extending the
        deadline first means one of them queries and the rest return
        immediately, instead of all of them stampeding the same aggregate.
        A read that then fails simply leaves the previous set in place for one
        interval — stale bias is a far smaller problem than a blocked chat.
        """
        now = self._now()
        if self._fresh_until is not None and now < self._fresh_until:
            return
        self._fresh_until = now + self._refresh_every

        rows = await repo.stats_by_model(since=now - self._window)
        penalized = frozenset(
            row.model_id
            for row in rows
            if should_penalize(row, min_votes=self._min_votes, down_rate_threshold=self._threshold)
        )
        if penalized != self._penalized:
            logger.info(
                "feedback penalties updated count=%s models=%s",
                len(penalized),
                ",".join(sorted(penalized)),
            )
        self._penalized = penalized
