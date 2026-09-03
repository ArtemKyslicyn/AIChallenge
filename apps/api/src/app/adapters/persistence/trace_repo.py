"""Run-trace repository: writes the journal, reads the Lab's window.

Like the other repositories here, ``save`` flushes and never commits — the
chat use case owns that transaction and decides when a trace becomes durable.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import RunTraceRow
from app.application.pareto import aggregate_models
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
    )


class SqlAlchemyRunTraceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save(self, trace: RunTrace) -> None:
        self._db.add(to_row(trace))
        await self._db.flush()

    async def list_for_session(self, session_id: UUID) -> list[RunTrace]:
        """Newest first — a debug panel asks "why this model *just now*"."""
        stmt = (
            select(RunTraceRow)
            .where(RunTraceRow.session_id == session_id)
            .order_by(RunTraceRow.created_at.desc(), RunTraceRow.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [to_trace(row) for row in rows]

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
        return aggregate_models(to_trace(row) for row in rows)
