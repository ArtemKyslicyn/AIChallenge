"""The threshold rule and the cache that keeps it out of the request path."""

from datetime import UTC, datetime, timedelta

import pytest
from fakes import StubFeedbackStats

from app.adapters.llm.feedback_penalties import FeedbackPenaltyCache, should_penalize
from app.domain.feedback import ModelFeedbackStats

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def stats(model_id: str = "m", *, ups: int = 0, downs: int = 0) -> ModelFeedbackStats:
    return ModelFeedbackStats(model_id=model_id, ups=ups, downs=downs)


@pytest.mark.parametrize(
    ("ups", "downs", "expected"),
    [
        (0, 0, False),  # nobody voted
        (0, 4, False),  # 100% down, but under the vote floor
        (0, 5, True),  # 100% down, exactly at the floor
        (7, 3, False),  # 30% down over ten votes
        (2, 8, True),  # 80% down over ten votes
        (4, 6, True),  # exactly at the threshold counts as bad
        (5, 6, False),  # 54% — just under
        (100, 0, False),  # loved and busy
    ],
)
def test_penalty_needs_both_a_bad_rate_and_enough_votes(
    ups: int, downs: int, expected: bool
) -> None:
    assert (
        should_penalize(stats(ups=ups, downs=downs), min_votes=5, down_rate_threshold=0.6)
        is expected
    )


class Clock:
    """A hand-wound clock, so "60 seconds later" is an assignment, not a sleep."""

    def __init__(self) -> None:
        self.value = NOW

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


@pytest.fixture
def clock() -> Clock:
    return Clock()


def cache(
    clock: Clock, *, refresh_seconds: int = 60, window_seconds: int = 86400
) -> FeedbackPenaltyCache:
    return FeedbackPenaltyCache(
        min_votes=5,
        down_rate_threshold=0.6,
        window_seconds=window_seconds,
        refresh_seconds=refresh_seconds,
        now=clock,
    )


async def test_nothing_is_penalized_before_the_first_refresh(clock: Clock) -> None:
    penalties = cache(clock)
    assert penalties.is_penalized("m") is False
    assert penalties.penalized == frozenset()


async def test_refresh_penalizes_only_the_models_over_the_threshold(clock: Clock) -> None:
    repo = StubFeedbackStats(
        stats("bad", ups=1, downs=9),
        stats("good", ups=9, downs=1),
        stats("quiet", ups=0, downs=2),
    )
    penalties = cache(clock)

    await penalties.refresh(repo)

    assert penalties.penalized == frozenset({"bad"})
    assert penalties.is_penalized("bad") is True
    assert penalties.is_penalized("good") is False
    assert penalties.is_penalized("quiet") is False


async def test_the_window_is_how_far_back_votes_count(clock: Clock) -> None:
    repo = StubFeedbackStats()
    await cache(clock, window_seconds=3600).refresh(repo)
    assert repo.last_since == NOW - timedelta(hours=1)


async def test_a_second_refresh_inside_the_interval_reads_nothing(clock: Clock) -> None:
    repo = StubFeedbackStats(stats("bad", ups=0, downs=9))
    penalties = cache(clock, refresh_seconds=60)

    await penalties.refresh(repo)
    clock.advance(59)
    await penalties.refresh(repo)

    assert repo.calls == 1


async def test_the_interval_expiring_lets_the_set_change(clock: Clock) -> None:
    repo = StubFeedbackStats(stats("bad", ups=0, downs=9))
    penalties = cache(clock, refresh_seconds=60)
    await penalties.refresh(repo)

    repo.rows = [stats("bad", ups=9, downs=9)]
    clock.advance(61)
    await penalties.refresh(repo)

    assert repo.calls == 2
    assert penalties.penalized == frozenset()


async def test_a_failing_read_raises_but_keeps_the_previous_set(clock: Clock) -> None:
    # The caller decides what a failure means; the cache must not silently
    # blank the bias it already has.
    repo = StubFeedbackStats(stats("bad", ups=0, downs=9))
    penalties = cache(clock, refresh_seconds=60)
    await penalties.refresh(repo)

    repo.fail = True
    clock.advance(61)
    with pytest.raises(RuntimeError):
        await penalties.refresh(repo)

    assert penalties.penalized == frozenset({"bad"})


async def test_a_failed_read_still_holds_the_interval_open(clock: Clock) -> None:
    # Otherwise every request during an outage would retry the same query.
    repo = StubFeedbackStats(fail=True)
    penalties = cache(clock, refresh_seconds=60)
    with pytest.raises(RuntimeError):
        await penalties.refresh(repo)

    clock.advance(30)
    await penalties.refresh(repo)
    assert repo.calls == 1
