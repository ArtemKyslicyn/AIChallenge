"""Unit tests for free-cloud media tools and intent detection."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from app.adapters.media.fake import FakeMediaGenerator
from app.adapters.media.store import DiskMediaStore
from app.application.media_tools import (
    SessionMediaRateLimiter,
    detect_media_intent,
    execute_media_tool,
    maybe_needs_media_tools,
)
from app.domain.media import (
    IMAGE_TOOL_NAME,
    VIDEO_TOOL_NAME,
    ToolCallRequest,
    parse_openai_tool_calls,
)


def test_detect_image_intent() -> None:
    calls = detect_media_intent("Нарисуй рыжего кота на крыше")
    assert len(calls) == 1
    assert calls[0].name == IMAGE_TOOL_NAME
    assert "кот" in calls[0].arguments["prompt"].casefold() or "рыж" in calls[0].arguments[
        "prompt"
    ].casefold()


def test_detect_video_intent() -> None:
    calls = detect_media_intent("Сделай короткое видео тумана над рекой")
    assert len(calls) == 1
    assert calls[0].name == VIDEO_TOOL_NAME


def test_soft_media_gate() -> None:
    assert maybe_needs_media_tools("нарисуй закат")
    assert not maybe_needs_media_tools("сколько будет 2+2?")


@pytest.mark.asyncio
async def test_fake_image_and_store(tmp_path: Path) -> None:
    gen = FakeMediaGenerator()
    store = DiskMediaStore(tmp_path)
    limiter = SessionMediaRateLimiter(image_limit=5, video_limit=2)
    session_id = uuid4()
    result = await execute_media_tool(
        ToolCallRequest(id="1", name=IMAGE_TOOL_NAME, arguments={"prompt": "cat", "model": "flux"}),
        generator=gen,
        store=store,
        session_id=session_id,
        limiter=limiter,
    )
    assert result.error is None
    assert result.media_url and result.media_url.startswith("/api/v1/media/")
    assert "![" in result.markdown
    media_id = result.media_url.rsplit("/", 1)[-1]
    loaded = await store.get(media_id)
    assert loaded is not None
    assert loaded[1] == "image/jpeg"


@pytest.mark.asyncio
async def test_video_without_key_returns_tool_error(tmp_path: Path) -> None:
    gen = FakeMediaGenerator(fail_video=True)
    store = DiskMediaStore(tmp_path)
    limiter = SessionMediaRateLimiter(image_limit=5, video_limit=2)
    result = await execute_media_tool(
        ToolCallRequest(id="1", name=VIDEO_TOOL_NAME, arguments={"prompt": "fog"}),
        generator=gen,
        store=store,
        session_id=uuid4(),
        limiter=limiter,
    )
    assert result.error
    assert "PIXAZO" in result.error or "Видео" in result.error


def test_parse_openai_tool_calls() -> None:
    calls = parse_openai_tool_calls(
        {
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {
                        "name": "generate_image",
                        "arguments": '{"prompt":"a fox","model":"sana"}',
                    },
                }
            ]
        }
    )
    assert calls[0].arguments["model"] == "sana"
    assert calls[0].arguments["prompt"] == "a fox"
