"""The two feedback reads against a real Postgres — the joins are the point."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.adapters.persistence.feedback_repo import SqlAlchemyFeedbackRepository
from app.adapters.persistence.models import MessageFeedbackRow, MessageRow, RunTraceRow, SessionRow
from app.domain.feedback import MessageFeedback

pytestmark = pytest.mark.skipif(not os.getenv("RUN_INTEGRATION"), reason="set RUN_INTEGRATION=1")

NOW = datetime.now(UTC)
SESSION_ID = UUID(int=42)


async def seed(engine: AsyncEngine, *, answers: list[tuple[UUID, str]]) -> None:
    """One session, one question, and one answer row per model under test."""
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
        # Flushed before the messages: without ORM relationships the unit of
        # work has no reason to order the two inserts for us.
        await db.flush()
        db.add(
            MessageRow(
                id=UUID(int=1),
                session_id=SESSION_ID,
                role="user",
                content="как дела?",
                created_at=NOW - timedelta(minutes=9),
            )
        )
        for index, (message_id, model_id) in enumerate(answers):
            db.add(
                MessageRow(
                    id=message_id,
                    session_id=SESSION_ID,
                    role="assistant",
                    content=f"ответ {index}",
                    model_id=model_id,
                    created_at=NOW - timedelta(minutes=8 - index),
                )
            )
        await db.commit()


def vote(message_id: UUID, value: str, *, minutes_ago: int = 1) -> MessageFeedback:
    return MessageFeedback(
        id=uuid4(),
        message_id=message_id,
        session_id=SESSION_ID,
        visitor_hash="v-hash",
        value="up" if value == "up" else "down",
        created_at=NOW - timedelta(minutes=minutes_ago),
    )


async def test_a_second_vote_replaces_the_first(engine: AsyncEngine) -> None:
    await seed(engine, answers=[(UUID(int=2), "model-a")])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        repo = SqlAlchemyFeedbackRepository(db)
        await repo.upsert(vote(UUID(int=2), "up"))
        await db.commit()
        stored = await repo.upsert(vote(UUID(int=2), "down"))
        await db.commit()

        assert stored.value == "down"
        current = await repo.get_for_message(UUID(int=2))
        assert current is not None and current.value == "down"
        rows = (await db.execute(MessageFeedbackRow.__table__.select())).all()
        assert len(rows) == 1


async def test_stats_group_by_the_model_that_answered(engine: AsyncEngine) -> None:
    await seed(engine, answers=[(UUID(int=2), "model-a"), (UUID(int=3), "model-b")])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        repo = SqlAlchemyFeedbackRepository(db)
        await repo.upsert(vote(UUID(int=2), "down"))
        await repo.upsert(vote(UUID(int=3), "up"))
        await db.commit()

        stats = {s.model_id: s for s in await repo.stats_by_model(since=NOW - timedelta(hours=1))}
        assert stats["model-a"].downs == 1 and stats["model-a"].ups == 0
        assert stats["model-b"].ups == 1
        assert stats["model-a"].down_rate == 1.0


async def test_stats_ignore_votes_older_than_the_window(engine: AsyncEngine) -> None:
    await seed(engine, answers=[(UUID(int=2), "model-a")])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        repo = SqlAlchemyFeedbackRepository(db)
        await repo.upsert(vote(UUID(int=2), "down", minutes_ago=120))
        await db.commit()
        assert await repo.stats_by_model(since=NOW - timedelta(hours=1)) == []


async def test_export_joins_the_trace_and_hides_content_by_default(engine: AsyncEngine) -> None:
    await seed(engine, answers=[(UUID(int=2), "model-a")])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(
            RunTraceRow(
                id=uuid4(),
                session_id=SESSION_ID,
                message_id=UUID(int=2),
                visitor_hash="v-hash",
                preferred_model="auto",
                resolved_model_id="model-a",
                attempts=[{"model_id": "model-x", "ok": False, "reason": "http_429"}],
                ttft_ms=120,
                total_ms=900,
                token_count_est=10,
                cost_proxy=1.0,
                tool_rounds=0,
                tool_ok=None,
                status="ok",
                created_at=NOW - timedelta(minutes=5),
            )
        )
        repo = SqlAlchemyFeedbackRepository(db)
        await repo.upsert(vote(UUID(int=2), "up"))
        await db.commit()

        rows = [row async for row in repo.export_rows(since=NOW - timedelta(hours=1), until=NOW)]
        (row,) = rows
        assert row.model_id == "model-a"
        assert row.feedback == "up"
        assert row.ttft_ms == 120 and row.total_ms == 900
        assert [a.model_id for a in row.attempts] == ["model-x"]
        assert row.prompt is None and row.answer is None


async def test_export_can_include_the_question_and_the_answer(engine: AsyncEngine) -> None:
    await seed(engine, answers=[(UUID(int=2), "model-a")])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        repo = SqlAlchemyFeedbackRepository(db)
        await repo.upsert(vote(UUID(int=2), "up"))
        await db.commit()

        rows = [
            row
            async for row in repo.export_rows(
                since=NOW - timedelta(hours=1), until=NOW, include_content=True
            )
        ]
        (row,) = rows
        assert row.prompt == "как дела?"
        assert row.answer == "ответ 0"


async def test_export_survives_an_answer_with_no_trace(engine: AsyncEngine) -> None:
    await seed(engine, answers=[(UUID(int=2), "model-a")])
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        repo = SqlAlchemyFeedbackRepository(db)
        await repo.upsert(vote(UUID(int=2), "down"))
        await db.commit()

        (row,) = [r async for r in repo.export_rows(since=NOW - timedelta(hours=1), until=NOW)]
        assert row.attempts == []
        assert row.ttft_ms is None
