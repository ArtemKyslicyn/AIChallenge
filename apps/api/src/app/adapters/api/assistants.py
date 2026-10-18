"""Assistants feature HTTP — real-task (day 35) on the stand."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.application.real_task import run_release_changelog_task
from app.core.deps import Container, get_container
from app.domain.entities import AUTO_MODEL

router = APIRouter(prefix="/assistants", tags=["assistants"])


class RealTaskRequest(BaseModel):
    goal: str | None = Field(default=None, max_length=2000)
    model: str = AUTO_MODEL


class RealTaskResponse(BaseModel):
    goal: str
    steps: list[str]
    review_markdown: str
    changelog: str
    model_id: str


@router.post("/real-task", response_model=RealTaskResponse)
async def real_task(
    body: RealTaskRequest,
    request: Request,
    container: Annotated[Container, Depends(get_container)],
) -> RealTaskResponse:
    _ = request
    result = await run_release_changelog_task(
        router=container.router,
        probe_enabled=container.settings.llm_probe_enabled,
        preferred_model=body.model or AUTO_MODEL,
        goal=body.goal,
    )
    return RealTaskResponse(
        goal=result.goal,
        steps=list(result.steps),
        review_markdown=result.review_markdown,
        changelog=result.changelog,
        model_id=result.model_id,
    )
