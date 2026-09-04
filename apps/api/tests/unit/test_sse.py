import json
from uuid import UUID

from app.adapters.api.sse import SSE_HEADERS, event_to_frame, to_sse
from app.application.chat import (
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


def _parse(frame: str) -> tuple[str, dict]:
    assert frame.endswith("\n\n")
    name_line, data_line = frame.rstrip("\n").split("\n")
    assert name_line.startswith("event: ")
    assert data_line.startswith("data: ")
    return name_line[len("event: ") :], json.loads(data_line[len("data: ") :])


def test_model_frame() -> None:
    assert _parse(event_to_frame(ModelEvent(model_id="m-1"))) == ("model", {"model_id": "m-1"})


def test_token_frame_keeps_whitespace_and_unicode() -> None:
    name, data = _parse(event_to_frame(TokenEvent(text="привет ")))
    assert (name, data) == ("token", {"text": "привет "})


def test_token_frame_escapes_newlines_rather_than_breaking_the_frame() -> None:
    frame = event_to_frame(TokenEvent(text="a\nb"))
    # A raw newline inside data would terminate the event early.
    assert frame.count("\n") == 3
    assert _parse(frame)[1] == {"text": "a\nb"}


def test_message_end_frame_carries_canonical_attribution() -> None:
    event = MessageEndEvent(message_id=UUID(int=1), content="hi", model_id="m-1")
    name, data = _parse(event_to_frame(event))
    assert name == "message_end"
    assert data == {
        "message_id": str(UUID(int=1)),
        "content": "hi",
        "model_id": "m-1",
        # Never absent and never null: "off" is the answer for every turn the
        # cascade did not touch, which is all of them by default.
        "cascade_stage": "off",
    }


def test_message_end_frame_reports_an_escalation() -> None:
    event = MessageEndEvent(
        message_id=UUID(int=2), content="hi", model_id="m-2", cascade_stage="escalated"
    )
    assert _parse(event_to_frame(event))[1]["cascade_stage"] == "escalated"


def test_error_frame() -> None:
    assert _parse(event_to_frame(ErrorEvent(message="nope"))) == ("error", {"message": "nope"})


def test_tool_frames() -> None:
    start = _parse(event_to_frame(ToolStartEvent(name="generate_image", call_id="c1")))
    assert start == ("tool_start", {"name": "generate_image", "call_id": "c1"})
    result = _parse(
        event_to_frame(
            ToolResultEvent(
                name="generate_image",
                call_id="c1",
                status="ok",
                media_url="/api/v1/media/x",
                provider_label="Pollinations flux",
            )
        )
    )
    assert result[0] == "tool_result"
    assert result[1]["media_url"] == "/api/v1/media/x"


def test_comic_frames() -> None:
    start = _parse(
        event_to_frame(
            ComicStartEvent(
                comic_id="c1",
                title="Metro",
                panel_count=3,
                characters=[{"id": "a", "name": "Cat", "look": "tabby"}],
                layout="single_page",
            )
        )
    )
    assert start[0] == "comic_start"
    assert start[1]["panel_count"] == 3
    assert start[1]["layout"] == "single_page"
    panel = _parse(
        event_to_frame(
            ComicPanelEvent(
                comic_id="c1",
                index=1,
                status="ok",
                text_mode="bubble",
                image_url="/api/v1/media/p.jpg",
                speaker="a",
                dialogue="Hi",
            )
        )
    )
    assert panel == (
        "comic_panel",
        {
            "comic_id": "c1",
            "index": 1,
            "status": "ok",
            "image_url": "/api/v1/media/p.jpg",
            "speaker": "a",
            "dialogue": "Hi",
            "caption": None,
            "text_mode": "bubble",
            "error": None,
        },
    )
    end = _parse(event_to_frame(ComicEndEvent(comic_id="c1", ok_count=2, fail_count=1)))
    assert end[1]["ok_count"] == 2


def test_headers_disable_proxy_buffering() -> None:
    assert SSE_HEADERS["X-Accel-Buffering"] == "no"
    assert "no-cache" in SSE_HEADERS["Cache-Control"]


async def test_to_sse_streams_every_event() -> None:
    async def events():
        yield ModelEvent(model_id="m-1")
        yield TokenEvent(text="hi")

    frames = [f async for f in to_sse(events())]
    assert [_parse(f)[0] for f in frames] == ["model", "token"]


async def test_to_sse_with_keepalive_emits_ping_while_waiting() -> None:
    import asyncio

    from app.adapters.api.sse import KEEPALIVE_FRAME, to_sse_with_keepalive

    async def events():
        await asyncio.sleep(0.05)
        yield ModelEvent(model_id="m-1")

    frames = [f async for f in to_sse_with_keepalive(events(), interval_seconds=0.02)]
    assert KEEPALIVE_FRAME in frames
    assert any(f.startswith("event: model") for f in frames)
