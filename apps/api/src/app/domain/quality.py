"""Quality domain: what a judge thought of one answer.

Sub-scores are kept, not just their average: when a rubric turns out to be
badly calibrated, the only way to see *which* criterion is misfiring is to have
kept them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

#: Критерии рубрики. Порядок фиксирован — по нему собирается промпт и разбор.
RUBRIC_CRITERIA = ("relevance", "completeness", "clarity")
#: Верхняя граница одного критерия. G-Eval-style form filling, шкала 0..5.
CRITERION_MAX = 5


@dataclass(frozen=True, slots=True)
class QualityVerdict:
    """Одна оценка одного ответа, 0..1, плюс из чего она сложилась."""

    score: float
    sub_scores: dict[str, int] = field(default_factory=dict)
    judge_model_id: str = ""


class AnswerJudge(Protocol):
    """Оценивает один ответ. Возвращает None, когда оценить не удалось.

    None — это «не знаем», а не «плохо»: подстановка нуля превратила бы сбой
    разбора в приговор модели.

    ``answered_by`` обязателен, а не опционален: судья должен уметь отказаться
    оценивать собственный текст, и без имени автора он этого не может.
    """

    async def judge(
        self, question: str, answer: str, *, answered_by: str
    ) -> QualityVerdict | None: ...
