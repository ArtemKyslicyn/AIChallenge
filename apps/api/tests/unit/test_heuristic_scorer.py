"""One test per signal the scorer can see, because each is a routing decision."""

import pytest

from app.adapters.llm.heuristic_scorer import HeuristicAnswerScorer

Q = "Объясни, чем очередь отличается от стека."


@pytest.fixture
def scorer() -> HeuristicAnswerScorer:
    return HeuristicAnswerScorer(min_answer_chars=40, threshold=0.75)


def test_accepts_a_complete_answer(scorer: HeuristicAnswerScorer) -> None:
    answer = (
        "Очередь работает по принципу FIFO, а стек — по принципу LIFO. "
        "Это определяет, какой элемент извлекается первым."
    )
    assert scorer.score(Q, answer).accepted is True


def test_rejects_an_empty_answer(scorer: HeuristicAnswerScorer) -> None:
    verdict = scorer.score(Q, "   ")
    assert verdict.accepted is False
    assert verdict.reason == "too_short"


def test_rejects_a_refusal(scorer: HeuristicAnswerScorer) -> None:
    answer = "Извините, как языковая модель я не могу ответить на этот вопрос сейчас."
    assert scorer.score(Q, answer).reason == "refusal"


def test_rejects_a_truncated_answer(scorer: HeuristicAnswerScorer) -> None:
    answer = "Очередь работает по принципу FIFO, а стек по принципу LIFO, и поэтому"
    assert scorer.score(Q, answer).reason == "truncated"


def test_rejects_an_unclosed_code_fence(scorer: HeuristicAnswerScorer) -> None:
    answer = "Вот пример на Python, он показывает разницу между структурами:\n```python\nq = []"
    assert scorer.score(Q, answer).reason == "unclosed_code"


def test_rejects_a_language_switch(scorer: HeuristicAnswerScorer) -> None:
    answer = (
        "A queue is a FIFO structure while a stack is LIFO, "
        "which decides what comes out first."
    )
    assert scorer.score(Q, answer).reason == "language_mismatch"


def test_a_bulleted_answer_is_not_truncated(scorer: HeuristicAnswerScorer) -> None:
    answer = "Ключевые различия между этими структурами данных:\n- очередь: FIFO\n- стек: LIFO"
    assert scorer.score(Q, answer).accepted is True


def test_an_english_question_may_be_answered_in_english(scorer: HeuristicAnswerScorer) -> None:
    # The language check only fires when the question itself was Russian.
    question = "What is the difference between a queue and a stack?"
    answer = "A queue is FIFO and a stack is LIFO, which decides what comes out first."
    assert scorer.score(question, answer).accepted is True


def test_a_closed_code_block_is_fine(scorer: HeuristicAnswerScorer) -> None:
    answer = "Вот минимальный пример на Python:\n```python\nq = []\n```"
    assert scorer.score(Q, answer).accepted is True


def test_the_score_is_the_share_of_checks_that_passed(scorer: HeuristicAnswerScorer) -> None:
    # Exactly one of the four signals fires, so three quarters survive — but a
    # single failed check is still a rejection, whatever the threshold says.
    verdict = scorer.score(Q, "Очередь работает по принципу FIFO, а стек по принципу LIFO и")
    assert verdict.score == pytest.approx(0.75)
    assert verdict.accepted is False
