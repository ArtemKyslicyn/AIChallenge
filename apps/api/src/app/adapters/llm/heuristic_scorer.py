"""A scorer that costs nothing: no model call, only what the text itself shows.

FrugalGPT trains a scorer. Training one here would spend exactly the budget the
cascade exists to save, so v1 asks the cheapest possible question instead: does
this answer *look* finished, on-topic and in the right language?
"""

from __future__ import annotations

import re

from app.domain.cascade import ScoreVerdict

#: Фразы отказа. Дешёвые модели отказываются заметно чаще дорогих, и это
#: самый однозначный повод эскалировать.
REFUSAL_MARKERS = (
    "как языковая модель",
    "я не могу",
    "не могу помочь",
    "не могу ответить",
    "as an ai language model",
    "i cannot",
    "i can't help",
    "i'm unable to",
)

#: Символы, на которых законченная фраза имеет право закончиться.
TERMINAL_CHARS = ".!?…:»)`\"'"

CYRILLIC = re.compile(r"[а-яёА-ЯЁ]")
LATIN = re.compile(r"[a-zA-Z]")

#: Признаков ровно столько, сколько проверок ниже: ``score`` — их доля.
CHECKS = 4


def _script_share(text: str) -> tuple[float, float]:
    cyr = len(CYRILLIC.findall(text))
    lat = len(LATIN.findall(text))
    total = cyr + lat
    if total == 0:
        return 0.0, 0.0
    return cyr / total, lat / total


class HeuristicAnswerScorer:
    """Каждая проверка — один голос. ``score`` — доля пройденных."""

    def __init__(self, min_answer_chars: int = 40, threshold: float = 0.75) -> None:
        self._min_chars = min_answer_chars
        self._threshold = threshold

    def score(self, question: str, answer: str) -> ScoreVerdict:
        text = answer.strip()

        # Порядок важен: слишком короткий ответ нечего проверять дальше, и
        # «обрыв» на нём был бы ложным объяснением.
        if len(text) < self._min_chars or not text:
            return ScoreVerdict(score=0.0, accepted=False, reason="too_short")

        failures: list[str] = []
        lowered = text.lower()

        if any(marker in lowered for marker in REFUSAL_MARKERS):
            failures.append("refusal")

        if text.count("```") % 2 == 1:
            failures.append("unclosed_code")

        if self._looks_truncated(text):
            failures.append("truncated")

        if self._language_switched(question, text):
            failures.append("language_mismatch")

        score = (CHECKS - len(failures)) / CHECKS
        return ScoreVerdict(
            score=score,
            # Both conditions on purpose: the threshold tunes how much evidence
            # is needed, but a single hard signal is already a "no".
            accepted=not failures and score >= self._threshold,
            reason=failures[0] if failures else "",
        )

    @staticmethod
    def _looks_truncated(text: str) -> bool:
        lines = text.rstrip().splitlines()
        last_line = lines[-1].rstrip() if lines else ""
        # Списки и код заканчиваются без точки на законных основаниях.
        if last_line.startswith(("-", "*", "#", ">", "|", "```")) or last_line[:1].isdigit():
            return False
        return last_line[-1:] not in TERMINAL_CHARS

    @staticmethod
    def _language_switched(question: str, answer: str) -> bool:
        q_cyr, _ = _script_share(question)
        a_cyr, a_lat = _script_share(answer)
        if q_cyr < 0.5:  # вопрос не по-русски — сравнивать нечего
            return False
        # Код и термины латиницей — норма, поэтому порог грубый.
        return a_lat > 0.7 and a_cyr < 0.2
