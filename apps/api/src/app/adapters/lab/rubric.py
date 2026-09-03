"""The judge's rubric, loaded from YAML under configs/lab/.

Same shape as :mod:`app.adapters.lab.presets`: unreadable configuration is a
warning and an absent result, never an exception. Here that also decides the
feature — no rubric means no judge, and a chat that behaves exactly as it did
before is a far better failure than a process that will not start.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

#: Файл рубрики внутри каталога lab. Именованный, а не glob: в этом каталоге
#: уже лежат пресеты задач, и брать «первый попавшийся YAML» было бы лотереей.
RUBRIC_FILENAME = "judge_rubric.yaml"

#: Плейсхолдеры шаблона. Подставляются заменой, потому что шаблон содержит
#: пример JSON — и ``str.format`` споткнулся бы о его фигурные скобки.
QUESTION_PLACEHOLDER = "{question}"
ANSWER_PLACEHOLDER = "{answer}"


@dataclass(slots=True, frozen=True)
class JudgeRubric:
    system: str
    template: str

    def render(self, question: str, answer: str) -> str:
        return self.template.replace(QUESTION_PLACEHOLDER, question).replace(
            ANSWER_PLACEHOLDER, answer
        )


def load_judge_rubric(lab_dir: Path) -> JudgeRubric | None:
    """``None`` when there is no usable rubric — the caller then builds no judge."""
    path = lab_dir / RUBRIC_FILENAME
    if not path.is_file():
        logger.info("judge rubric not found at %s; judge stays off", path)
        return None
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("judge rubric unreadable %s: %s", path.name, exc)
        return None
    if not isinstance(data, dict):
        logger.warning("judge rubric %s is not a mapping", path.name)
        return None

    system = str(data.get("system") or "").strip()
    template = str(data.get("template") or "").strip()
    if not system or not template:
        logger.warning("judge rubric %s needs both `system` and `template`", path.name)
        return None
    # Шаблон без обоих плейсхолдеров судил бы пустоту и всегда одинаково.
    if QUESTION_PLACEHOLDER not in template or ANSWER_PLACEHOLDER not in template:
        logger.warning(
            "judge rubric %s must contain %s and %s",
            path.name,
            QUESTION_PLACEHOLDER,
            ANSWER_PLACEHOLDER,
        )
        return None
    return JudgeRubric(system=system, template=template)
