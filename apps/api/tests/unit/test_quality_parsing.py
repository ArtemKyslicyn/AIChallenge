"""Reading a judge's answer, and deciding what is worth judging at all.

Both are pure functions on purpose: the sampler takes its dice roll as an
argument instead of calling ``random`` itself, so the gates can be asserted
without patching a module.
"""

import pytest

from app.application.quality import parse_verdict, prose_chars, should_judge


def test_parses_a_clean_verdict() -> None:
    verdict = parse_verdict('{"relevance": 5, "completeness": 4, "clarity": 3}', judge_model_id="j")
    assert verdict is not None
    assert verdict.score == pytest.approx(12 / 15)
    assert verdict.judge_model_id == "j"
    assert verdict.sub_scores == {"relevance": 5, "completeness": 4, "clarity": 3}


def test_parses_a_verdict_wrapped_in_a_code_fence() -> None:
    raw = '```json\n{"relevance": 5, "completeness": 5, "clarity": 5}\n```'
    verdict = parse_verdict(raw, judge_model_id="j")
    assert verdict is not None and verdict.score == 1.0


def test_parses_a_verdict_with_prose_around_it() -> None:
    # Модели любят предисловие, даже когда просят «строго JSON».
    raw = 'Вот оценка:\n{"relevance": 0, "completeness": 0, "clarity": 0}\nГотово.'
    verdict = parse_verdict(raw, judge_model_id="j")
    assert verdict is not None and verdict.score == 0.0


@pytest.mark.parametrize(
    "raw",
    [
        "это не json вовсе",
        "",
        "{}",
        '{"relevance": 5, "clarity": 5}',  # нет completeness
        '{"relevance": 9, "completeness": 5, "clarity": 5}',  # вне диапазона
        '{"relevance": -1, "completeness": 5, "clarity": 5}',
        '{"relevance": "пять", "completeness": 5, "clarity": 5}',
        '{"relevance": true, "completeness": 5, "clarity": 5}',  # bool — не оценка
        '{"relevance": 4.5, "completeness": 5, "clarity": 5}',
        '["relevance", 5]',
    ],
)
def test_a_broken_verdict_is_none_not_zero(raw: str) -> None:
    # Ноль означал бы «судья счёл ответ плохим». Сбой разбора — это «не знаем».
    assert parse_verdict(raw, judge_model_id="j") is None


def test_sampler_respects_the_status_and_length_gates() -> None:
    assert (
        should_judge(
            status="error",
            answer_chars=500,
            rate=1.0,
            roll=0.0,
            judged_this_hour=0,
            max_per_hour=60,
        )
        is False
    )
    assert (
        should_judge(
            status="ok",
            answer_chars=10,
            rate=1.0,
            roll=0.0,
            judged_this_hour=0,
            max_per_hour=60,
            min_answer_chars=80,
        )
        is False
    )


def test_sampler_respects_the_hourly_cap_and_the_rate() -> None:
    common = dict(status="ok", answer_chars=500, min_answer_chars=80)
    assert should_judge(**common, rate=1.0, roll=0.0, judged_this_hour=60, max_per_hour=60) is False
    assert should_judge(**common, rate=0.2, roll=0.5, judged_this_hour=0, max_per_hour=60) is False
    assert should_judge(**common, rate=0.2, roll=0.1, judged_this_hour=0, max_per_hour=60) is True


def test_a_rate_of_zero_judges_nothing() -> None:
    # roll всегда >= 0, поэтому строгое «<» — единственное, что выключает выборку.
    assert (
        should_judge(
            status="ok",
            answer_chars=500,
            rate=0.0,
            roll=0.0,
            judged_this_hour=0,
            max_per_hour=60,
        )
        is False
    )


def test_prose_chars_ignores_media_markup() -> None:
    # Ответ из одной картинки нечего оценивать по рубрике текста.
    media = "![Изображение](https://example.test/a.png)\n\n_Pollinations_"
    assert prose_chars(media) == 0
    assert prose_chars(media + "\n\nВот кот, которого вы просили.") > 0
