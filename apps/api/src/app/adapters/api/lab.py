"""Lab API — YAML preset tasks, and the model ranking over recent run traces."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from app.adapters.lab.presets import load_lab_presets
from app.application.pareto import PARETO_FORMULA
from app.core.deps import RunTraces, get_container, utcnow

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
    #: Null when nothing in the window was measured — the UI shows a dash, and
    #: must never render it as 0 or NaN.
    p50_ttft_ms: float | None
    p50_total_ms: float | None
    avg_cost_proxy: float | None
    score: float


class ParetoResponse(BaseModel):
    formula: str
    hours: int
    models: list[ModelAggregateResponse]


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
    rows = await traces.aggregate(since=until - timedelta(hours=hours), until=until)
    return ParetoResponse(
        formula=PARETO_FORMULA,
        hours=hours,
        models=[
            ModelAggregateResponse(
                model_id=row.model_id,
                n=row.n,
                success_rate=row.success_rate,
                p50_ttft_ms=row.p50_ttft_ms,
                p50_total_ms=row.p50_total_ms,
                avg_cost_proxy=row.avg_cost_proxy,
                score=row.score,
            )
            for row in rows
        ],
    )
