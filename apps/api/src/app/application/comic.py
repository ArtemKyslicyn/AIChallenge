"""Comic storyboard parsing, image prompts, and message persistence fence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

COMIC_FENCE_START = "```comic+json"
COMIC_FENCE_END = "```"
NO_TEXT_CLAUSE = (
    "no text, no letters, no words, no captions, no speech bubbles, no watermarks"
)
_FOREGROUND_CLAUSE = (
    "cartoon comic characters in the foreground, clear action pose, "
    "not an empty cityscape, not architecture photography, not a building facade"
)
_BUBBLE_MAX_CHARS = 90
_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")
_FENCE_RE = re.compile(
    r"```comic\+json\s*([\s\S]*?)```",
    re.IGNORECASE,
)
_DIALOGUE_KEYS = ("dialogue", "line", "speech", "text", "said", "replica", "реплика")


@dataclass(slots=True)
class ComicCharacter:
    id: str
    name: str
    look: str


@dataclass(slots=True)
class ComicPanel:
    index: int
    visual: str
    speaker: str | None
    dialogue: str | None
    caption: str | None
    text_mode: str  # bubble | caption | both
    image_url: str | None = None
    status: str = "pending"  # pending | ok | error
    error: str | None = None


@dataclass(slots=True)
class ComicStoryboard:
    title: str
    style: str
    seed: int
    characters: list[ComicCharacter] = field(default_factory=list)
    panels: list[ComicPanel] = field(default_factory=list)
    comic_id: str = field(default_factory=lambda: uuid4().hex[:12])
    #: One Pollinations page that contains the whole strip (preferred v1 layout).
    page_image_url: str | None = None
    layout: str = "single_page"  # single_page | per_panel (legacy)

    def character_map(self) -> dict[str, ComicCharacter]:
        return {c.id: c for c in self.characters}


def choose_text_mode(*, dialogue: str | None, caption: str | None) -> str:
    d = (dialogue or "").strip()
    c = (caption or "").strip()
    if d and c:
        return "both"
    if c and not d:
        return "caption"
    if d and len(d) > _BUBBLE_MAX_CHARS:
        return "caption"
    if d:
        return "bubble"
    if c:
        return "caption"
    return "caption"


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def parse_storyboard_json(raw: str | dict[str, Any]) -> ComicStoryboard:
    if isinstance(raw, dict):
        data = raw
    else:
        text = (raw or "").strip()
        if not text:
            raise ValueError("empty storyboard")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = _JSON_BLOCK.search(text)
            if not match:
                raise ValueError("storyboard JSON not found") from None
            data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("storyboard must be an object")

    characters: list[ComicCharacter] = []
    for i, item in enumerate(data.get("characters") or []):
        if not isinstance(item, dict):
            continue
        cid = _as_str(item.get("id")) or f"c{i + 1}"
        characters.append(
            ComicCharacter(
                id=cid,
                name=_as_str(item.get("name")) or cid,
                look=_as_str(item.get("look")) or "distinct comic character",
            )
        )

    panels_raw = data.get("panels") or []
    if not isinstance(panels_raw, list):
        raise ValueError("panels must be a list")
    panels: list[ComicPanel] = []
    for i, item in enumerate(panels_raw[:6]):
        if not isinstance(item, dict):
            continue
        dialogue = _panel_dialogue(item)
        caption = _as_str(item.get("caption")) or None
        mode = _as_str(item.get("text_mode")).lower()
        if mode not in {"bubble", "caption", "both"}:
            mode = choose_text_mode(dialogue=dialogue, caption=caption)
        # Long dialogue without caption → move to caption for readability
        if mode == "bubble" and dialogue and len(dialogue) > _BUBBLE_MAX_CHARS:
            caption = caption or dialogue
            dialogue = None if caption == dialogue else dialogue
            mode = "caption" if not dialogue else "both"
        panels.append(
            ComicPanel(
                index=i + 1,
                visual=_as_str(item.get("visual") or item.get("scene") or item.get("description"))
                or "comic panel scene with characters in the foreground",
                speaker=_as_str(item.get("speaker")) or None,
                dialogue=dialogue,
                caption=caption,
                text_mode=mode,
            )
        )

    if len(panels) < 3:
        raise ValueError(f"need 3–6 panels, got {len(panels)}")
    panels = panels[:6]

    seed_raw = data.get("seed")
    try:
        seed = int(seed_raw) if seed_raw is not None else int(uuid4().int % 2_147_483_647)
    except (TypeError, ValueError):
        seed = int(uuid4().int % 2_147_483_647)

    board = ComicStoryboard(
        title=_as_str(data.get("title")) or "Comic",
        style=_as_str(data.get("style"))
        or "clean comic book illustration, consistent characters, flat colors, bold ink outlines",
        seed=seed,
        characters=characters,
        panels=panels,
        comic_id=_as_str(data.get("comic_id")) or uuid4().hex[:12],
    )
    normalize_storyboard_speech(board)
    return board


def _panel_dialogue(item: dict[str, Any]) -> str | None:
    for key in _DIALOGUE_KEYS:
        value = _as_str(item.get(key))
        if value:
            return value
    return None


def character_looks_line(board: ComicStoryboard) -> str:
    if not board.characters:
        return "main comic characters in the foreground, highly detailed and consistent"
    parts = [f"{c.name} ({c.id}): {c.look}" for c in board.characters]
    return "Character bible (identical in every panel): " + " | ".join(parts)


def page_layout_instruction(panel_count: int) -> str:
    n = max(3, min(6, panel_count))
    if n == 3:
        return "one comic page with 3 equal panels in a single horizontal row, thick black gutters"
    if n == 4:
        return "one comic page with a 2x2 panel grid, thick black gutters between panels"
    if n == 5:
        return (
            "one comic page with 5 panels: two on the top row and three on the bottom row, "
            "thick black gutters"
        )
    return "one comic page with a 2-column by 3-row panel grid, thick black gutters"


def page_image_size(panel_count: int) -> tuple[int, int]:
    n = max(3, min(6, panel_count))
    if n <= 3:
        return 1280, 640
    if n == 4:
        return 1024, 1024
    return 1024, 1408


def build_comic_page_prompt(board: ComicStoryboard) -> str:
    """Single-image comic page: all panels inside one artwork, no baked-in text."""
    n = len(board.panels)
    beats: list[str] = []
    for panel in board.panels:
        scene = panel.visual.strip() or f"panel {panel.index} with the main characters"
        beats.append(f"Panel {panel.index}: {scene}")
    parts = [
        f"Detailed {board.style or 'bold ink comic book'} illustration",
        page_layout_instruction(n),
        "Each panel shows a DIFFERENT moment of the same story; characters stay visually identical",
        character_looks_line(board),
        "Story beats: " + " // ".join(beats),
        _FOREGROUND_CLAUSE,
        "high detail faces, clothing folds, props, consistent proportions across panels",
        NO_TEXT_CLAUSE,
        "leave empty space near the top of each panel for speech bubbles",
    ]
    return ". ".join(p for p in parts if p)


def panel_seed(board: ComicStoryboard, panel: ComicPanel) -> int:
    """Legacy per-panel seed (unused when layout is single_page)."""
    return int(board.seed) + int(panel.index) * 1009


def build_panel_image_prompt(board: ComicStoryboard, panel: ComicPanel) -> str:
    """Legacy single-panel prompt (kept for tests / future per_panel mode)."""
    looks = character_looks_line(board)
    scene = panel.visual.strip() or f"comic panel {panel.index} with the main characters"
    parts = [
        f"Comic panel {panel.index} of {len(board.panels)}: {scene}",
        looks,
        board.style or "clean comic book illustration, flat colors, bold outlines",
        _FOREGROUND_CLAUSE,
        NO_TEXT_CLAUSE,
    ]
    return ". ".join(p for p in parts if p)


def normalize_storyboard_speech(board: ComicStoryboard) -> None:
    """Guarantee each panel has readable HTML overlay text."""
    for panel in board.panels:
        if panel.dialogue or panel.caption:
            if panel.text_mode not in {"bubble", "caption", "both"}:
                panel.text_mode = choose_text_mode(
                    dialogue=panel.dialogue, caption=panel.caption
                )
            continue
        who = panel.speaker or "Герой"
        panel.dialogue = f"{who}: …"
        panel.text_mode = "bubble"


def storyboard_narration(board: ComicStoryboard) -> str:
    lines = [f"**{board.title}**", "", "Персонажи:"]
    if board.characters:
        for c in board.characters:
            lines.append(f"- **{c.name}** — {c.look}")
    else:
        lines.append("- (по сюжету)")
    lines.append("")
    lines.append(f"Раскадровка ({len(board.panels)} панелей):")
    for p in board.panels:
        bit = p.dialogue or p.caption or "…"
        who = p.speaker or "—"
        lines.append(f"{p.index}. [{who}] {bit}")
    lines.append("")
    return "\n".join(lines)


def storyboard_to_persist_dict(board: ComicStoryboard) -> dict[str, Any]:
    return {
        "comic_id": board.comic_id,
        "title": board.title,
        "style": board.style,
        "seed": board.seed,
        "layout": board.layout,
        "page_image_url": board.page_image_url,
        "characters": [
            {"id": c.id, "name": c.name, "look": c.look} for c in board.characters
        ],
        "panels": [
            {
                "index": p.index,
                "visual": p.visual,
                "speaker": p.speaker,
                "dialogue": p.dialogue,
                "caption": p.caption,
                "text_mode": p.text_mode,
                "image_url": p.image_url or board.page_image_url,
                "status": p.status,
                "error": p.error,
            }
            for p in board.panels
        ],
    }


def serialize_comic_fence(board: ComicStoryboard) -> str:
    payload = json.dumps(storyboard_to_persist_dict(board), ensure_ascii=False, indent=2)
    return f"\n\n{COMIC_FENCE_START}\n{payload}\n{COMIC_FENCE_END}\n"


def extract_comic_from_content(content: str) -> ComicStoryboard | None:
    match = _FENCE_RE.search(content or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
        board = parse_storyboard_json(data)
        page_url = _as_str(data.get("page_image_url")) or None
        layout = _as_str(data.get("layout")) or "single_page"
        board.layout = layout if layout in {"single_page", "per_panel"} else "single_page"
        board.page_image_url = page_url
        # Restore panel media status from persisted fields
        for i, panel in enumerate(board.panels):
            raw = (data.get("panels") or [])[i] if isinstance(data.get("panels"), list) else {}
            if isinstance(raw, dict):
                panel.image_url = _as_str(raw.get("image_url")) or page_url
                panel.status = _as_str(raw.get("status")) or ("ok" if panel.image_url else "error")
                panel.error = _as_str(raw.get("error")) or None
            elif page_url:
                panel.image_url = page_url
                panel.status = "ok"
        return board
    except (json.JSONDecodeError, ValueError, TypeError, IndexError):
        return None


def strip_comic_fence(content: str) -> str:
    return _FENCE_RE.sub("", content or "").strip()


STORYBOARD_SYSTEM = """You are a comic storyboard planner for a SINGLE comic page image.
Return ONLY one JSON object (no markdown) with keys:
title, style, seed (int), characters[{id,name,look}], panels[{index,visual,speaker,dialogue,caption,text_mode}].
Rules:
- panels length must be between 3 and 6 inclusive; choose count from the story.
- Prefer keeping the user's dialogue wording when they supplied lines.
- EVERY panel MUST include non-empty dialogue (spoken line) OR caption (narration). Prefer dialogue.
- characters.look MUST be a rich English description (at least ~20 words each): species/age vibe,
  face, hair/fur/metal, eye color, clothing with colors, signature props, body silhouette.
  These looks will be copied into ONE page image so consistency depends on your detail.
- visual: English description of THIS panel only — different camera/action than other panels.
  Lead with who is doing what. Background is secondary.
  Never ask for text/letters/bubbles in the image.
- text_mode: "bubble" for short spoken lines, "caption" for narration or long text, "both" when needed.
- style: short consistent art direction (e.g. "bold ink comic, flat cel shading, clean gutters").
"""
