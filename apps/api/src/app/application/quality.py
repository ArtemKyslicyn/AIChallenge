"""Reading a judge's verdict, and deciding what is worth judging at all.

Two pure functions and nothing else. The sampler takes its dice roll as an
argument rather than calling :mod:`random` itself, so every gate can be
asserted directly instead of through a patched module; the caller passes
``random.random()``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.domain.quality import CRITERION_MAX, RUBRIC_CRITERIA, QualityVerdict
from app.domain.tracing import STATUS_OK

logger = logging.getLogger(__name__)

#: Первый JSON-объект в ответе. Модели добавляют предисловие даже когда их
#: просят «строго JSON», и отбрасывать такой ответ целиком — терять оценку,
#: которая на самом деле есть.
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

#: Медиа-разметка, которую вставляют инструменты: картинка плюс подпись
#: провайдера курсивом. Ответ, состоящий только из неё, нечего оценивать
#: рубрикой, написанной про текст.
_MEDIA_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_PROVIDER_CAPTION = re.compile(r"^_[^_\n]*_$", re.MULTILINE)


def parse_verdict(raw: str, *, judge_model_id: str) -> QualityVerdict | None:
    """``None`` whenever the answer cannot be read as a full, in-range form.

    Never ``0.0``: zero is a verdict ("the judge found this bad"), and a failed
    parse is the absence of one. Substituting zero would let a flaky judge
    quietly demote a model in the ranking.
    """
    match = _JSON_OBJECT.search(raw or "")
    if match is None:
        logger.info("judge verdict discarded reason=no_json judge=%s", judge_model_id)
        return None
    try:
        parsed: Any = json.loads(match.group(0))
    except ValueError:
        logger.info("judge verdict discarded reason=bad_json judge=%s", judge_model_id)
        return None
    if not isinstance(parsed, dict):
        logger.info("judge verdict discarded reason=not_an_object judge=%s", judge_model_id)
        return None

    sub_scores: dict[str, int] = {}
    for criterion in RUBRIC_CRITERIA:
        if criterion not in parsed:
            logger.info(
                "judge verdict discarded reason=missing_criterion criterion=%s judge=%s",
                criterion,
                judge_model_id,
            )
            return None
        value = parsed[criterion]
        # ``bool`` is an ``int`` in Python, and ``True`` would silently become
        # a score of 1. A judge that answered with a boolean did not fill in
        # the form.
        if isinstance(value, bool) or not isinstance(value, int):
            logger.info(
                "judge verdict discarded reason=not_an_int criterion=%s judge=%s",
                criterion,
                judge_model_id,
            )
            return None
        if not 0 <= value <= CRITERION_MAX:
            logger.info(
                "judge verdict discarded reason=out_of_range criterion=%s judge=%s",
                criterion,
                judge_model_id,
            )
            return None
        sub_scores[criterion] = value

    total = sum(sub_scores.values())
    return QualityVerdict(
        score=total / (len(RUBRIC_CRITERIA) * CRITERION_MAX),
        sub_scores=sub_scores,
        judge_model_id=judge_model_id,
    )


def prose_chars(answer: str) -> int:
    """How much of this answer is text a rubric can actually read.

    An answer that is only a generated image plus its provider caption has
    nothing to be relevant, complete or clear *about* — judging it would spend
    a call to learn that a picture is not a paragraph.
    """
    text = _MEDIA_IMAGE.sub("", answer or "")
    text = _PROVIDER_CAPTION.sub("", text)
    return len(text.strip())


def should_judge(
    *,
    status: str,
    answer_chars: int,
    rate: float,
    roll: float,
    judged_this_hour: int,
    max_per_hour: int,
    min_answer_chars: int = 0,
) -> bool:
    """The gates, cheapest first, in the order that costs the least to refuse.

    The hourly cap comes before the dice on purpose: once the budget is spent
    the answer is the same for every roll, and spending randomness on a
    foregone conclusion would make the cap look probabilistic.
    """
    if status != STATUS_OK:
        return False
    if answer_chars < min_answer_chars:
        return False
    if judged_this_hour >= max_per_hour:
        return False
    return roll < rate
