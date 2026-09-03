"""Scheduling the judge: what it is allowed to touch, and what it never is.

Every test here defends one of three promises. The judge is not on the path of
the request; it cannot break the answer or the trace when it fails; and with no
``JUDGE_MODEL`` configured it does not exist at all, so the chat behaves exactly
as it did before this feature was written.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from uuid import UUID

import pytest

from app.adapters.api.sessions import schedule_judgement
from app.adapters.llm.llm_judge import HourlyJudgeBudget
from app.application.chat import ReplyDraft
from app.core.deps import build_container
from app.core.settings import Settings
from app.domain.quality import QualityVerdict
from app.domain.tracing import STATUS_ERROR, STATUS_OK

MESSAGE_ID = UUID(int=7)
ANSWER = "Достаточно длинный ответ, чтобы пройти порог длины, " * 3
VERDICT = QualityVerdict(score=0.8, sub_scores={"relevance": 4}, judge_model_id="judge-1")


class FakeJudge:
    def __init__(
        self,
        verdict: QualityVerdict | None = VERDICT,
        *,
        delay: float = 0.0,
        error: Exception | None = None,
    ) -> None:
        self.verdict, self.delay, self.error = verdict, delay, error
        self.calls = 0
        self.started = asyncio.Event()
        self.seen: tuple[str, str, str] | None = None

    async def judge(self, question: str, answer: str, *, answered_by: str) -> QualityVerdict | None:
        self.calls += 1
        self.seen = (question, answer, answered_by)
        self.started.set()
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.verdict


class FakeResult:
    rowcount = 1


class FakeDb:
    """Just enough session for the real repository to run its UPDATE."""

    def __init__(self) -> None:
        self.statements: list[Any] = []
        self.commits = 0
        self.closed = False

    async def __aenter__(self) -> FakeDb:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        self.closed = True
        return False

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult()

    async def commit(self) -> None:
        self.commits += 1


class FakeContainer:
    """The three things scheduling reads off the container, and nothing else."""

    def __init__(self, judge: FakeJudge | None, **overrides: Any) -> None:
        # Rate 1.0 by default so the dice never decide a test's outcome; the
        # sampling itself is asserted where it is the subject.
        knobs: dict[str, Any] = {"judge_sample_rate": 1.0, **overrides}
        self.settings = Settings(
            _env_file=None,  # type: ignore[call-arg]
            use_fake_llm=True,
            **knobs,
        )
        self.judge = judge
        self.judge_budget = HourlyJudgeBudget()
        self.sessions_opened: list[FakeDb] = []

    def sessionmaker(self) -> FakeDb:
        db = FakeDb()
        self.sessions_opened.append(db)
        return db


def draft(*, status: str = STATUS_OK, text: str = ANSWER) -> ReplyDraft:
    return ReplyDraft(
        message_id=MESSAGE_ID, chunks=[text], model_id="answer-model", finished=True, status=status
    )


async def test_no_judge_model_configured_means_no_call_at_all() -> None:
    container = FakeContainer(judge=None)
    assert schedule_judgement(container, "вопрос?", draft()) is None  # type: ignore[arg-type]
    assert container.sessions_opened == []


def test_an_empty_judge_model_builds_no_judge_at_all() -> None:
    # The off switch is the absence of the object, not a flag checked later.
    container = build_container(Settings(_env_file=None, use_fake_llm=True))  # type: ignore[call-arg]
    assert container.judge is None


def test_a_configured_judge_model_builds_one() -> None:
    container = build_container(
        Settings(_env_file=None, use_fake_llm=True, judge_model="judge-1")  # type: ignore[call-arg]
    )
    assert container.judge is not None


async def test_the_judge_is_never_awaited_inside_the_stream() -> None:
    # A judge that sleeps far longer than this test: if scheduling waited for
    # it, the assertion below would never be reached.
    judge = FakeJudge(delay=30.0)
    container = FakeContainer(judge)
    started = time.monotonic()
    task = schedule_judgement(container, "вопрос?", draft())  # type: ignore[arg-type]
    assert time.monotonic() - started < 0.5
    assert task is not None and not task.done()

    await asyncio.wait_for(judge.started.wait(), timeout=1.0)
    assert container.sessions_opened == []
    task.cancel()


async def test_a_verdict_reaches_the_trace_of_that_message() -> None:
    judge = FakeJudge()
    container = FakeContainer(judge)
    task = schedule_judgement(container, "вопрос?", draft())  # type: ignore[arg-type]
    assert task is not None
    await task

    assert judge.seen == ("вопрос?", ANSWER, "answer-model")
    (db,) = container.sessions_opened
    assert db.commits == 1 and db.closed
    compiled = str(db.statements[0])
    assert "UPDATE run_traces" in compiled


async def test_a_failing_judge_leaves_the_answer_and_the_trace_alone() -> None:
    judge = FakeJudge(error=RuntimeError("provider exploded"))
    container = FakeContainer(judge)
    task = schedule_judgement(container, "вопрос?", draft())  # type: ignore[arg-type]
    assert task is not None
    await task  # must not raise: the chat is already over, nobody can handle this

    assert container.sessions_opened == []


async def test_an_unreadable_verdict_writes_nothing() -> None:
    # None is "we do not know", and not knowing is not a row worth writing.
    container = FakeContainer(FakeJudge(verdict=None))
    task = schedule_judgement(container, "вопрос?", draft())  # type: ignore[arg-type]
    assert task is not None
    await task
    assert container.sessions_opened == []


async def test_a_turn_that_did_not_end_ok_is_not_judged() -> None:
    container = FakeContainer(FakeJudge())
    assert schedule_judgement(container, "в?", draft(status=STATUS_ERROR)) is None  # type: ignore[arg-type]


async def test_a_short_answer_is_not_judged() -> None:
    container = FakeContainer(FakeJudge())
    assert schedule_judgement(container, "в?", draft(text="Да.")) is None  # type: ignore[arg-type]


async def test_an_answer_that_is_only_an_image_is_not_judged() -> None:
    # There is nothing for a text rubric to find relevant or complete here.
    picture = "![кот](/media/a.png)\n_Pollinations_"
    container = FakeContainer(FakeJudge())
    assert schedule_judgement(container, "в?", draft(text=picture)) is None  # type: ignore[arg-type]


async def test_a_rescued_answer_nobody_finished_is_not_judged() -> None:
    container = FakeContainer(FakeJudge())
    unfinished = draft()
    unfinished.finished = False
    assert schedule_judgement(container, "в?", unfinished) is None  # type: ignore[arg-type]


async def test_the_hourly_cap_stops_scheduling() -> None:
    container = FakeContainer(FakeJudge(), judge_max_per_hour=2)
    tasks = [
        schedule_judgement(container, "в?", draft())  # type: ignore[arg-type]
        for _ in range(4)
    ]
    assert [t is not None for t in tasks] == [True, True, False, False]
    await asyncio.gather(*[t for t in tasks if t is not None])
    assert container.judge_budget.used() == 2


async def test_the_sample_rate_can_refuse_the_turn() -> None:
    container = FakeContainer(FakeJudge(), judge_sample_rate=0.0)
    assert schedule_judgement(container, "в?", draft()) is None  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("judge_model", ""),
        ("judge_sample_rate", 0.2),
        ("judge_min_answer_chars", 80),
        ("judge_max_per_hour", 60),
        ("judge_min_runs", 5),
        ("judge_timeout_seconds", 20.0),
    ],
)
def test_the_judge_defaults_are_the_ones_the_spec_names(name: str, expected: object) -> None:
    settings = Settings(_env_file=None, use_fake_llm=True)  # type: ignore[call-arg]
    assert getattr(settings, name) == expected
