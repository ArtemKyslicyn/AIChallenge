"""Assistants feature HTTP — real-task (day 35) on the stand."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.adapters.api.auth import OptionalAuthUser
from app.adapters.api.local_llm import load_user_source, source_model_ids
from app.application.local_llm import local_llm_scope, prefer_local_model
from app.application.local_llm_rate_limit import charge_local_pin
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
    auth_user: OptionalAuthUser,
    container: Annotated[Container, Depends(get_container)],
) -> RealTaskResponse:
    source = await load_user_source(request, auth_user)
    local_ids = source_model_ids(source)
    preferred = prefer_local_model(body.model, local_model_ids=local_ids)
    charge_local_pin(
        container.local_llm_limiter,
        user_id=None if auth_user is None else auth_user.id,
        models=[preferred],
    )
    async with local_llm_scope(source):
        result = await run_release_changelog_task(
            router=container.router,
            probe_enabled=container.settings.llm_probe_enabled,
            preferred_model=preferred,
            goal=body.goal,
        )
    return RealTaskResponse(
        goal=result.goal,
        steps=list(result.steps),
        review_markdown=result.review_markdown,
        changelog=result.changelog,
        model_id=result.model_id,
    )
