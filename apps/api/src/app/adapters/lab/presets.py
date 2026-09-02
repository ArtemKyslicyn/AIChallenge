"""Lab task presets from YAML under configs/lab/."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
_SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


@dataclass(slots=True, frozen=True)
class LabPreset:
    id: str
    title: str
    category: str
    difficulty: str
    task: str
    golden_answer: str
    golden_hint: str
    rubric: str


def load_lab_presets(lab_dir: Path) -> list[LabPreset]:
    if not lab_dir.is_dir():
        logger.warning("lab presets dir missing: %s", lab_dir)
        return []
    presets: list[LabPreset] = []
    for path in sorted(lab_dir.glob("*.yaml")):
        try:
            data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as exc:
            logger.warning("skip lab preset %s: %s", path.name, exc)
            continue
        if not isinstance(data, dict):
            continue
        preset_id = str(data.get("id") or path.stem)
        if not _SAFE_ID.match(preset_id):
            continue
        task = str(data.get("task") or "").strip()
        if not task:
            continue
        presets.append(
            LabPreset(
                id=preset_id,
                title=str(data.get("title") or preset_id).strip(),
                category=str(data.get("category") or "general").strip(),
                difficulty=str(data.get("difficulty") or "medium").strip(),
                task=task,
                golden_answer=str(data.get("golden_answer") or "").strip(),
                golden_hint=str(data.get("golden_hint") or "").strip(),
                rubric=str(data.get("rubric") or "").strip(),
            )
        )
    return presets
