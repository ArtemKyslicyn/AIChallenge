"""Lab presets API — YAML tasks for the prompt-strategy laboratory."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.adapters.lab.presets import load_lab_presets
from app.core.deps import get_container

router = APIRouter(prefix="/lab", tags=["lab"])


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
