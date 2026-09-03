"""Run-trace repository: writes the journal, reads the Lab's window.

Like the other repositories here, ``save`` flushes and never commits — the
chat use case owns that transaction and decides when a trace becomes durable.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import RunTraceRow
from app.application.pareto import DEFAULT_MIN_JUDGED_RUNS, aggregate_models
from app.domain.cascade import (
    CASCADE_CHEAP,
    CASCADE_ESCALATED,
    CASCADE_OFF,
    CascadeSummary,
    cascade_summary_from_counts,
)
from app.domain.tracing import AttemptRecord, ModelAggregate, RunTrace

#: Ceiling on one aggregation read. A window of "last 30 days" on a busy
#: instance would otherwise pull the whole table into memory to compute a p50.
AGGREGATE_ROW_LIMIT = 5000


def attempt_to_json(attempt: AttemptRecord) -> dict[str, Any]:
    return {
        "model_id": attempt.model_id,
        "ok": attempt.ok,
        "reason": attempt.reason,
        "ttft_ms": attempt.ttft_ms,
        "error_kind": attempt.error_kind,
    }


def attempt_from_json(raw: Mapping[str, Any]) -> AttemptRecord:
    """Tolerant on purpose: an old row must not break today's debug view."""
    return AttemptRecord(
        model_id=str(raw.get("model_id") or ""),
        ok=bool(raw.get("ok", False)),
        reason=str(raw.get("reason") or ""),
        ttft_ms=raw.get("ttft_ms"),
        error_kind=raw.get("error_kind"),
    )


def to_row(trace: RunTrace) -> RunTraceRow:
    return RunTraceRow(
        id=trace.id,
        session_id=trace.session_id,
        message_id=trace.message_id,
        visitor_hash=trace.visitor_hash,
        preferred_model=trace.preferred_model,
        resolved_model_id=trace.resolved_model_id,
        attempts=[attempt_to_json(a) for a in trace.attempts],
        ttft_ms=trace.ttft_ms,
        total_ms=trace.total_ms,
        token_count_est=trace.token_count_est,
        cost_proxy=trace.cost_proxy,
        tool_rounds=trace.tool_rounds,
        tool_ok=trace.tool_ok,
        status=trace.status,
        created_at=trace.created_at,
        cascade_stage=trace.cascade_stage,
        cheap_model_id=trace.cheap_model_id,
        cheap_score=trace.cheap_score,
        quality_score=trace.quality_score,
        quality_model_id=trace.quality_model_id,
    )


def to_trace(row: RunTraceRow) -> RunTrace:
    return RunTrace(
        id=row.id,
        session_id=row.session_id,
        message_id=row.message_id,
        visitor_hash=row.visitor_hash,
        preferred_model=row.preferred_model,
        resolved_model_id=row.resolved_model_id,
        attempts=[attempt_from_json(a) for a in row.attempts or []],
        ttft_ms=row.ttft_ms,
        total_ms=row.total_ms,
        token_count_est=row.token_count_est,
        cost_proxy=row.cost_proxy,
        tool_rounds=row.tool_rounds,
        tool_ok=row.tool_ok,
        status=row.status,
        created_at=row.created_at,
        # Tolerant like the attempts journal: a row written before migration
        # 005 has no stage, and must read back as "the cascade did not run".
        cascade_stage=row.cascade_stage or CASCADE_OFF,
        cheap_model_id=row.cheap_model_id,
        cheap_score=row.cheap_score,
        quality_score=row.quality_score,
        quality_model_id=row.quality_model_id,
    )


class SqlAlchemyRunTraceRepository:
    def __init__(
        self, db: AsyncSession, *, min_judged_runs: int = DEFAULT_MIN_JUDGED_RUNS
    ) -> None:
        self._db = db
        self._min_judged_runs = min_judged_runs

    async def save(self, trace: RunTrace) -> None:
        self._db.add(to_row(trace))
        await self._db.flush()

    async def set_quality(
        self, message_id: UUID, *, score: float, judge_model_id: str
    ) -> bool:
        """Attach a verdict to the trace of one message, long after the fact.

        An UPDATE rather than a read-modify-write: the judge runs seconds after
        the turn, on a session of its own, and re-saving a whole entity read at
        that point would let it overwrite anything the chat wrote in between.

        Returns whether a row was there to update. Nothing is wrong when there
        wasn't — tracing can be off, or the turn may have ended without one.
        """
        stmt = (
            update(RunTraceRow)
            .where(RunTraceRow.message_id == message_id)
            .values(quality_score=score, quality_model_id=judge_model_id)
        )
        # execute() is typed as returning a plain Result; only the cursor
        # flavour carries rowcount, and an UPDATE always produces one.
        result = cast("CursorResult[Any]", await self._db.execute(stmt))
        return bool(result.rowcount)

    async def list_for_session(self, session_id: UUID) -> list[RunTrace]:
        """Newest first — a debug panel asks "why this model *just now*"."""
        stmt = (
            select(RunTraceRow)
            .where(RunTraceRow.session_id == session_id)
            .order_by(RunTraceRow.created_at.desc(), RunTraceRow.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [to_trace(row) for row in rows]

    async def stages_for_session(self, session_id: UUID) -> dict[UUID, str]:
        """Which stage answered each message of one chat.

        One query for the whole thread rather than one per message, for the
        same reason the votes are read this way: history is rendered in a
        single response, and the badge must not cost it N round trips.

        Only stages worth drawing come back. ``off`` is the default for every
        message ever written — including user turns and answers from before
        the cascade existed — so shipping those rows would be shipping the
        absence of news.
        """
        stmt = select(RunTraceRow.message_id, RunTraceRow.cascade_stage).where(
            RunTraceRow.session_id == session_id,
            RunTraceRow.cascade_stage != CASCADE_OFF,
        )
        rows = (await self._db.execute(stmt)).all()
        return {message_id: str(stage) for message_id, stage in rows}

    async def aggregate(self, *, since: datetime, until: datetime) -> list[ModelAggregate]:
        """Percentiles are computed in Python over a bounded, recent slice.

        SQL could do the p50, but not the score, and one code path for the math
        (shared with the unit tests) is worth more here than one query.
        """
        stmt = (
            select(RunTraceRow)
            .where(RunTraceRow.created_at >= since, RunTraceRow.created_at <= until)
            .order_by(RunTraceRow.created_at.desc())
            .limit(AGGREGATE_ROW_LIMIT)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return aggregate_models(
            (to_trace(row) for row in rows), min_judged_runs=self._min_judged_runs
        )

    async def cascade_summary(
        self, *, since: datetime, until: datetime
    ) -> CascadeSummary | None:
        """How often the cheap stage was enough, over one window.

        Counted in SQL rather than over the aggregation slice: this is two
        integers, and pulling rows for it would put the summary under the same
        5000-row ceiling that exists for percentiles.
        """
        stmt = (
            select(RunTraceRow.cascade_stage, func.count())
            .where(
                RunTraceRow.created_at >= since,
                RunTraceRow.created_at <= until,
                RunTraceRow.cascade_stage != CASCADE_OFF,
            )
            .group_by(RunTraceRow.cascade_stage)
        )
        counts = {stage: total for stage, total in (await self._db.execute(stmt)).all()}
        return cascade_summary_from_counts(
            cheap=counts.get(CASCADE_CHEAP, 0),
            escalated=counts.get(CASCADE_ESCALATED, 0),
        )
