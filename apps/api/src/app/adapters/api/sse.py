"""Maps chat events onto the SSE wire format."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.application.chat import (
    ChatEvent,
    ComicEndEvent,
    ComicPanelEvent,
    ComicStartEvent,
    ErrorEvent,
    MessageEndEvent,
    ModelEvent,
    TokenEvent,
    ToolResultEvent,
    ToolStartEvent,
)

SSE_MEDIA_TYPE = "text/event-stream"

#: X-Accel-Buffering tells nginx not to sit on the stream; without it tokens
#: arrive in one burst at the end.
SSE_HEADERS = {
    "Cache-Control": "no-cache, no-transform",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

#: Comment frames keep proxies from closing idle long jobs (video poll, slow
#: first token). Clients ignore lines that start with `:`.
KEEPALIVE_FRAME = ": keepalive\n\n"
DEFAULT_KEEPALIVE_SECONDS = 15.0


def format_frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event_to_frame(event: ChatEvent) -> str:
    match event:
        case ModelEvent():
            return format_frame("model", {"model_id": event.model_id})
        case TokenEvent():
            return format_frame("token", {"text": event.text})
        case MessageEndEvent():
            return format_frame(
                "message_end",
                {
                    "message_id": str(event.message_id),
                    "content": event.content,
                    "model_id": event.model_id,
                    # Always present, never null: "off" is a real answer, and a
                    # client that has to distinguish absent from off would be
                    # guessing about a value the server always knows.
                    "cascade_stage": event.cascade_stage,
                },
            )
        case ErrorEvent():
            return format_frame("error", {"message": event.message})
        case ToolStartEvent():
            return format_frame(
                "tool_start",
                {"name": event.name, "call_id": event.call_id},
            )
        case ToolResultEvent():
            return format_frame(
                "tool_result",
                {
                    "name": event.name,
                    "call_id": event.call_id,
                    "status": event.status,
                    "media_url": event.media_url,
                    "provider_label": event.provider_label,
                    "error": event.error,
                },
            )
        case ComicStartEvent():
            return format_frame(
                "comic_start",
                {
                    "comic_id": event.comic_id,
                    "title": event.title,
                    "panel_count": event.panel_count,
                    "characters": event.characters,
                    "layout": event.layout,
                },
            )
        case ComicPanelEvent():
            return format_frame(
                "comic_panel",
                {
                    "comic_id": event.comic_id,
                    "index": event.index,
                    "status": event.status,
                    "image_url": event.image_url,
                    "speaker": event.speaker,
                    "dialogue": event.dialogue,
                    "caption": event.caption,
                    "text_mode": event.text_mode,
                    "error": event.error,
                },
            )
        case ComicEndEvent():
            return format_frame(
                "comic_end",
                {
                    "comic_id": event.comic_id,
                    "ok_count": event.ok_count,
                    "fail_count": event.fail_count,
                },
            )


async def _next_event(events: AsyncIterator[ChatEvent]) -> ChatEvent:
    """Wrap ``__anext__`` in a coroutine so it can be handed to ``create_task``.

    The async-iterator protocol only promises an ``Awaitable``, and a bare
    awaitable is not a coroutine — which is what ``create_task`` requires.
    """
    return await events.__anext__()


async def to_sse(events: AsyncIterator[ChatEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield event_to_frame(event)


async def to_sse_with_keepalive(
    events: AsyncIterator[ChatEvent],
    *,
    interval_seconds: float = DEFAULT_KEEPALIVE_SECONDS,
) -> AsyncIterator[str]:
    """Yield SSE frames; if the use-case is silent too long, emit comment pings."""
    if interval_seconds <= 0:
        async for frame in to_sse(events):
            yield frame
        return

    aiter = events.__aiter__()
    pending: asyncio.Task[ChatEvent] = asyncio.create_task(_next_event(aiter))
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval_seconds)
            if not done:
                yield KEEPALIVE_FRAME
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                break
            yield event_to_frame(event)
            pending = asyncio.create_task(_next_event(aiter))
    finally:
        if not pending.done():
            pending.cancel()
            try:
                await pending
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
