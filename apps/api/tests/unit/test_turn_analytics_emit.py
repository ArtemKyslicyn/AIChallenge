from __future__ import annotations

from uuid import uuid4

import pytest

from app.adapters.api.sessions import ANALYTICS_TEXT_MAX, _clip_analytics_text, _emit_turn_analytics
from app.application.chat import ReplyDraft
from app.domain.analytics import AnalyticsEvent


def test_clip_analytics_text_short() -> None:
    assert _clip_analytics_text("hello") == "hello"


def test_clip_analytics_text_long() -> None:
    long = "x" * (ANALYTICS_TEXT_MAX + 50)
    out = _clip_analytics_text(long)
    assert out.endswith("…[truncated]")
    assert len(out) == ANALYTICS_TEXT_MAX + len("…[truncated]")


class _CapturingAnalytics:
    def __init__(self) -> None:
        self.batches: list[list[AnalyticsEvent]] = []

    async def capture(self, events: list[AnalyticsEvent]) -> None:
        self.batches.append(list(events))


class _Container:
    def __init__(self, analytics: _CapturingAnalytics) -> None:
        self.analytics = analytics


@pytest.mark.asyncio
async def test_emit_turn_analytics_includes_prompt_answer_metrics() -> None:
    sink = _CapturingAnalytics()
    draft = ReplyDraft(
        message_id=uuid4(),
        chunks=["Ответ модели"],
        model_id="deepseek/deepseek-v4-flash",
        finished=True,
        status="ok",
        prompt="Вопрос?",
        latency_ms=1234,
        tokens_approx=12,
        cost_proxy=0.4,
    )
    await _emit_turn_analytics(
        _Container(sink),  # type: ignore[arg-type]
        distinct_id="visitor-1",
        session_id=uuid4(),
        draft=draft,
        prompt="Вопрос?",
    )
    assert len(sink.batches) == 1
    names = [e.name for e in sink.batches[0]]
    assert names == ["message_sent", "assistant_completed"]
    props = sink.batches[0][1].properties
    assert props["prompt"] == "Вопрос?"
    assert props["answer"] == "Ответ модели"
    assert props["model_id"] == "deepseek/deepseek-v4-flash"
    assert props["latency_ms"] == 1234
    assert props["tokens_approx"] == 12
    assert props["cost_proxy"] == 0.4
    assert props["status"] == "ok"
