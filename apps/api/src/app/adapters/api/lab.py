"""Lab API — preset tasks, the model ranking, and the feedback read models."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from app.adapters.lab.presets import load_lab_presets
from app.adapters.llm.feedback_penalties import should_penalize
from app.application.feedback import preference_row_json
from app.application.pareto import PARETO_FORMULA
from app.core.deps import (
    Feedback,
    RunTraces,
    get_container,
    resolve_visitor_identity,
    utcnow,
    visitor_id_header,
)
from app.core.settings import Settings

router = APIRouter(prefix="/lab", tags=["lab"])

#: 30 days. Wide enough for a monthly view, narrow enough that the aggregation
#: row cap stays a safety net rather than a routine truncation.
MAX_WINDOW_HOURS = 720


class LabPresetResponse(BaseModel):
    id: str
    title: str
    category: str
    difficulty: str
    task: str
    golden_answer: str = ""
    golden_hint: str = ""
    rubric: str = ""


@router.get("/presets", response_model=list[LabPresetResponse])
async def list_lab_presets(request: Request) -> list[LabPresetResponse]:
    settings = get_container(request).settings
    presets = load_lab_presets(settings.lab_path())
    return [
        LabPresetResponse(
            id=p.id,
            title=p.title,
            category=p.category,
            difficulty=p.difficulty,
            task=p.task,
            golden_answer=p.golden_answer,
            golden_hint=p.golden_hint,
            rubric=p.rubric,
        )
        for p in presets
    ]


class ModelAggregateResponse(BaseModel):
    model_id: str
    n: int
    success_rate: float
    #: Mean judge verdict over the judged runs only, 0..1. Null when nobody
    #: judged this model in the window — never 0.0, which would read as a
    #: verdict rather than as missing data.
    avg_quality: float | None
    #: How many runs that average is over. Published beside it because a mean
    #: without its sample size reads as a settled fact, and because the score
    #: only starts using quality once this passes ``JUDGE_MIN_RUNS``.
    judged_n: int
    #: Null when nothing in the window was measured — the UI shows a dash, and
    #: must never render it as 0 or NaN.
    p50_ttft_ms: float | None
    p50_total_ms: float | None
    avg_cost_proxy: float | None
    score: float


class CascadeSummaryResponse(BaseModel):
    """How often the cheap stage was enough, over the same window as the table."""

    total: int
    cheap: int
    escalated: int
    escalation_rate: float


class ParetoResponse(BaseModel):
    formula: str
    hours: int
    models: list[ModelAggregateResponse]
    #: Null when the cascade never ran in this window — switched off, or simply
    #: nothing to report. The panel draws the line only when it is present.
    cascade: CascadeSummaryResponse | None = None


@router.get("/pareto", response_model=ParetoResponse)
async def model_pareto(
    traces: RunTraces,
    hours: Annotated[int, Query(ge=1, le=MAX_WINDOW_HOURS)] = 24,
) -> ParetoResponse:
    """Ranked models over a recent window.

    Open like `/lab/presets`: every row is an aggregate keyed by model id and
    carries nothing about any visitor or conversation.
    """
    until = utcnow()
    since = until - timedelta(hours=hours)
    rows = await traces.aggregate(since=since, until=until)
    summary = await traces.cascade_summary(since=since, until=until)
    return ParetoResponse(
        formula=PARETO_FORMULA,
        hours=hours,
        cascade=(
            CascadeSummaryResponse(
                total=summary.total,
                cheap=summary.cheap,
                escalated=summary.escalated,
                escalation_rate=summary.escalation_rate,
            )
            if summary is not None
            else None
        ),
        models=[
            ModelAggregateResponse(
                model_id=row.model_id,
                n=row.n,
                success_rate=row.success_rate,
                avg_quality=row.avg_quality,
                judged_n=row.judged_n,
                p50_ttft_ms=row.p50_ttft_ms,
                p50_total_ms=row.p50_total_ms,
                avg_cost_proxy=row.avg_cost_proxy,
                score=row.score,
            )
            for row in rows
        ],
    )


class ModelFeedbackResponse(BaseModel):
    model_id: str
    ups: int
    downs: int
    down_rate: float
    #: True when this model is currently being demoted in the router's chain.
    #: The Lab shows it as a chip, so the ranking and the routing agree.
    penalized: bool


class FeedbackStatsResponse(BaseModel):
    hours: int
    models: list[ModelFeedbackResponse]


@router.get("/feedback-stats", response_model=FeedbackStatsResponse)
async def feedback_stats(
    request: Request,
    feedback: Feedback,
    hours: Annotated[int, Query(ge=1, le=MAX_WINDOW_HOURS)] = 24,
) -> FeedbackStatsResponse:
    """Up/down counts per model over a recent window.

    Open like `/lab/pareto`: a row is a model id and two integers.

    ``penalized`` is recomputed from these very counts rather than read off the
    router's cache, so the table answers "does this model qualify right now",
    not "had the cache noticed yet" — the two differ for at most one refresh
    interval, and the honest answer is the one the reader can verify.
    """
    settings = get_container(request).settings
    rows = await feedback.stats_by_model(since=utcnow() - timedelta(hours=hours))
    models = [
        ModelFeedbackResponse(
            model_id=row.model_id,
            ups=row.ups,
            downs=row.downs,
            down_rate=row.down_rate,
            penalized=should_penalize(
                row,
                min_votes=settings.feedback_min_votes,
                down_rate_threshold=settings.feedback_down_rate_threshold,
            ),
        )
        for row in rows
    ]
    # Worst first: the table exists to find the model that needs attention.
    # Ties broken by name so it does not reshuffle between reloads.
    models.sort(key=lambda m: (-m.down_rate, -(m.ups + m.downs), m.model_id))
    return FeedbackStatsResponse(hours=hours, models=models)


#: Deliberately the same wording as any other unknown path: when the export is
#: switched off, the endpoint should not even admit to existing.
EXPORT_NOT_FOUND = "Not Found"

NDJSON_MEDIA_TYPE = "application/x-ndjson"


async def require_export_access(
    request: Request,
    client_visitor_id: Annotated[str | None, Depends(visitor_id_header)] = None,
) -> str:
    """Two locks on the dump, and one answer when either is shut.

    Unlike the aggregate routes, an export line names a specific message. So it
    needs a configuration switch *and* an identified visitor — and a caller who
    has neither must not be able to tell which of the two stopped them.
    """
    settings: Settings = get_container(request).settings
    if not settings.feedback_export_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=EXPORT_NOT_FOUND)
    identity = resolve_visitor_identity(request, client_visitor_id)
    if identity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=EXPORT_NOT_FOUND)
    return identity[0]


ExportAccess = Annotated[str, Depends(require_export_access)]


@router.get("/preference-export")
async def preference_export(
    request: Request,
    feedback: Feedback,
    _access: ExportAccess,
    hours: Annotated[int, Query(ge=1, le=MAX_WINDOW_HOURS)] = 24,
) -> Response:
    """The preference dataset as NDJSON — one line per vote.

    Built in full before it is sent, rather than streamed. The row cap already
    bounds it to a download-sized body, and a plain response either succeeds or
    fails with a real status code instead of a 200 that dies halfway through
    somebody's file.
    """
    settings = get_container(request).settings
    until = utcnow()
    lines = [
        json.dumps(preference_row_json(row), ensure_ascii=False)
        async for row in feedback.export_rows(
            since=until - timedelta(hours=hours),
            until=until,
            include_content=settings.feedback_export_include_content,
        )
    ]
    body = "".join(line + "\n" for line in lines)
    return Response(
        content=body,
        media_type=NDJSON_MEDIA_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="preference-export-{hours}h.ndjson"'
        },
    )
