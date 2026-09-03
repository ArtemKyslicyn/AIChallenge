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
