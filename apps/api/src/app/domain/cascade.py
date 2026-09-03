"""Cascade domain: was a cheap answer good enough, and who ended up answering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

#: Каскад выключен или не применялся к этому ответу.
CASCADE_OFF = "off"
#: Ответила дешёвая модель, скорер её принял.
CASCADE_CHEAP = "cheap"
#: Дешёвый ответ отвергнут, отвечала модель из основной цепочки.
CASCADE_ESCALATED = "escalated"

CASCADE_STAGES = frozenset({CASCADE_OFF, CASCADE_CHEAP, CASCADE_ESCALATED})


@dataclass(frozen=True, slots=True)
class ScoreVerdict:
    """Что скорер думает об одном ответе.

    ``reason`` заполняется только при отказе и попадает в трейс: без него
    «эскалировали» — это факт без объяснения, и настраивать порог вслепую.
    """

    score: float
    accepted: bool
    reason: str = ""


class AnswerScorer(Protocol):
    """Решает, годится ли ответ дешёвой модели.

    v1 — эвристика без сетевых вызовов. Порт существует, чтобы LLM-скорер
    можно было подставить, не трогая use case.
    """

    def score(self, question: str, answer: str) -> ScoreVerdict: ...


@dataclass(frozen=True, slots=True)
class CascadeSummary:
    """One window of the cascade, as one sentence: how often cheap was enough.

    Not keyed by model: the question the Lab row answers is "is the cheap stage
    earning its latency", and that is a property of the window, not of any one
    model in it.
    """

    total: int
    cheap: int
    escalated: int

    @property
    def escalation_rate(self) -> float:
        return self.escalated / self.total if self.total else 0.0


def cascade_summary_from_counts(*, cheap: int, escalated: int) -> CascadeSummary | None:
    """``None`` when the cascade never ran in this window.

    Zeroes would claim it ran and escalated nothing, which is a different fact
    and would make the panel draw a row about a feature that is switched off.
    """
    total = cheap + escalated
    if total == 0:
        return None
    return CascadeSummary(total=total, cheap=cheap, escalated=escalated)
