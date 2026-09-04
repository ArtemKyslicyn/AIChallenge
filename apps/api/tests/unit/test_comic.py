"""Unit tests for comic storyboard helpers."""

from __future__ import annotations

import pytest

from app.application.comic import (
    NO_TEXT_CLAUSE,
    build_panel_image_prompt,
    choose_text_mode,
    extract_comic_from_content,
    parse_storyboard_json,
    serialize_comic_fence,
    storyboard_narration,
    strip_comic_fence,
)


def test_choose_text_mode_short_bubble() -> None:
    assert choose_text_mode(dialogue="Привет!", caption=None) == "bubble"


def test_choose_text_mode_long_caption() -> None:
    long = "а" * 120
    assert choose_text_mode(dialogue=long, caption=None) == "caption"


def test_parse_clamps_and_requires_min_panels() -> None:
    with pytest.raises(ValueError, match="3–6"):
        parse_storyboard_json(
            {
                "title": "x",
                "panels": [
                    {"visual": "a", "dialogue": "hi"},
                    {"visual": "b", "dialogue": "ho"},
                ],
            }
        )
    board = parse_storyboard_json(
        {
            "title": "Metro",
            "style": "ink comic",
            "seed": 7,
            "characters": [{"id": "a", "name": "Cat", "look": "orange tabby"}],
            "panels": [{"visual": f"scene {i}", "dialogue": "ok", "speaker": "a"} for i in range(8)],
        }
    )
    assert len(board.panels) == 6
    assert board.seed == 7


def test_panel_prompt_forbids_text() -> None:
    board = parse_storyboard_json(
        {
            "title": "T",
            "style": "flat comic",
            "characters": [{"id": "a", "name": "Bot", "look": "silver robot"}],
            "panels": [
                {"visual": "wide shot", "dialogue": "Hi", "speaker": "a"},
                {"visual": "close-up", "dialogue": "Yo", "speaker": "a"},
                {"visual": "exit", "caption": "The end"},
            ],
        }
    )
    prompt = build_panel_image_prompt(board, board.panels[0])
    assert "silver robot" in prompt
    assert NO_TEXT_CLAUSE.split(",")[0] in prompt
    assert "no speech bubbles" in prompt


def test_fence_roundtrip() -> None:
    board = parse_storyboard_json(
        {
            "title": "Round",
            "panels": [
                {"visual": "1", "dialogue": "A"},
                {"visual": "2", "dialogue": "B"},
                {"visual": "3", "caption": "fin"},
            ],
        }
    )
    board.panels[0].image_url = "/api/v1/media/abc.jpg"
    board.panels[0].status = "ok"
    fence = serialize_comic_fence(board)
    narration = storyboard_narration(board)
    content = narration + fence
    restored = extract_comic_from_content(content)
    assert restored is not None
    assert restored.title == "Round"
    assert restored.panels[0].image_url == "/api/v1/media/abc.jpg"
    assert "comic+json" not in strip_comic_fence(content)
