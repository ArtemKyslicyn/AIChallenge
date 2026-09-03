"""Migration 006 and the out-of-band verdict write, against a real Postgres.

The unit tests prove the arithmetic; only a real database proves that the two
columns exist, that an UPDATE from a second session lands on the right row, and
that the ranking window reads the verdict back.
"""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapters.persistence.models import MessageRow, SessionRow
from app.adapters.persistence.trace_repo import SqlAlchemyRunTraceRepository
from app.domain.tracing import STATUS_OK, RunTrace

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")

NOW = datetime.now(UTC)
SESSION_ID = UUID(int=77)


def trace(message_id: UUID, *, model_id: str = "model-a", minutes_ago: int = 5) -> RunTrace:
    return RunTrace(
        id=uuid4(),
        session_id=SESSION_ID,
        message_id=message_id,
        visitor_hash="v-hash",
        preferred_model="auto",
        resolved_model_id=model_id,
        attempts=[],
        ttft_ms=100,
        total_ms=1000,
        token_count_est=10,
        cost_proxy=1.0,
        tool_rounds=0,
        tool_ok=None,
        status=STATUS_OK,
        created_at=NOW - timedelta(minutes=minutes_ago),
    )


async def seed(engine: AsyncEngine, *, message_ids: list[UUID]) -> None:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(
            SessionRow(
                id=SESSION_ID,
                access_token="token",
                scenario_id="default",
                status="active",
                created_at=NOW - timedelta(minutes=10),
            )
        )
        await db.flush()
        for index, message_id in enumerate(message_ids):
            db.add(
                MessageRow(
                    id=message_id,
                    session_id=SESSION_ID,
                    role="assistant",
                    content=f"ответ {index}",
                    model_id="model-a",
                    created_at=NOW - timedelta(minutes=9 - index),
                )
            )
        repo = SqlAlchemyRunTraceRepository(db)
        for message_id in message_ids:
            await repo.save(trace(message_id))
        await db.commit()


async def test_a_verdict_written_from_another_session_lands_on_the_trace(
    engine: AsyncEngine,
) -> None:
    judged, untouched = UUID(int=1), UUID(int=2)
    await seed(engine, message_ids=[judged, untouched])

    maker = async_sessionmaker(engine, expire_on_commit=False)
    # A session of its own, exactly like the judge task uses.
    async with maker() as db:
        assert await SqlAlchemyRunTraceRepository(db).set_quality(
            judged, score=0.8, judge_model_id="judge-1"
        )
        await db.commit()

    async with maker() as db:
        rows = {
            t.message_id: t
            for t in await SqlAlchemyRunTraceRepository(db).list_for_session(SESSION_ID)
        }
        assert rows[judged].quality_score == 0.8
        assert rows[judged].quality_model_id == "judge-1"
        assert rows[untouched].quality_score is None
        assert rows[untouched].quality_model_id is None


async def test_setting_quality_on_an_untraced_message_is_not_a_failure(
    engine: AsyncEngine,
) -> None:
    await seed(engine, message_ids=[UUID(int=1)])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        assert (
            await SqlAlchemyRunTraceRepository(db).set_quality(
                UUID(int=999), score=0.5, judge_model_id="judge-1"
            )
            is False
        )


async def test_the_ranking_window_reads_the_verdicts_back(engine: AsyncEngine) -> None:
    message_ids = [UUID(int=i) for i in range(1, 4)]
    await seed(engine, message_ids=message_ids)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        repo = SqlAlchemyRunTraceRepository(db, min_judged_runs=2)
        for message_id in message_ids[:2]:
            await repo.set_quality(message_id, score=0.5, judge_model_id="judge-1")
        await db.commit()

        (agg,) = await repo.aggregate(since=NOW - timedelta(hours=1), until=NOW)
        assert agg.n == 3
        assert agg.judged_n == 2
        assert agg.avg_quality == 0.5
        # Two judged runs clear the threshold, so quality — not the 100%
        # success rate — is what the score now divides by latency and cost.
        assert agg.score == pytest.approx(0.5)
