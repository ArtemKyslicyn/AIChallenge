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
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# GET /image/{prompt} URLs break or ignore the tail when the path is huge.
_MAX_GET_PROMPT_CHARS = 700


def _panel_dialogue(item: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (dialogue, caption, speaker) from loose LLM shapes."""
    caption = _as_str(item.get("caption")) or None
    speaker = _as_str(item.get("speaker")) or None
    raw = None
    for key in _DIALOGUE_KEYS:
        if key in item and item.get(key) is not None:
            raw = item.get(key)
            break
    if isinstance(raw, dict):
        # {"cat": "Hi", "robot": "Yo", "caption": "..."}
        lines: list[str] = []
        for key, value in raw.items():
            if str(key).lower() in {"caption", "narration", "note"}:
                cap = _as_str(value)
                if cap:
                    caption = caption or cap
                continue
            text = _as_str(value)
            if not text:
                continue
            if speaker is None:
                speaker = str(key)
            lines.append(text if len(raw) == 1 else f"{key}: {text}")
        return (" / ".join(lines) if lines else None, caption, speaker)
    if isinstance(raw, list):
        bits = [_as_str(x) for x in raw if _as_str(x)]
        return (" / ".join(bits) if bits else None, caption, speaker)
    dialogue = _as_str(raw) if raw is not None else None
    return (dialogue or None, caption, speaker)


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
    #: Optional single-page art (legacy / experimental). Default is per_panel.
    page_image_url: str | None = None
    layout: str = "per_panel"  # per_panel | single_page

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
        dialogue, caption, speaker = _panel_dialogue(item)
        caption = caption or (_as_str(item.get("caption")) or None)
        speaker = speaker or (_as_str(item.get("speaker")) or None)
        mode = _as_str(item.get("text_mode")).lower()
        if mode not in {"bubble", "caption", "both"}:
            mode = choose_text_mode(dialogue=dialogue, caption=caption)
        # Long dialogue without caption → move to caption for readability
        if mode == "bubble" and dialogue and len(dialogue) > _BUBBLE_MAX_CHARS:
            caption = caption or dialogue
            dialogue = None if caption == dialogue else dialogue
            mode = "caption" if not dialogue else "both"
        visual = (
            _as_str(item.get("visual"))
            or _as_str(item.get("scene"))
            or _as_str(item.get("description"))
            or _as_str(item.get("desc"))
            or "comic panel scene with characters in the foreground"
        )
        panels.append(
            ComicPanel(
                index=i + 1,
                visual=visual,
                speaker=speaker,
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
        layout="per_panel",
    )
    normalize_storyboard_speech(board)
    return board


def _short_look(look: str, *, max_chars: int = 120) -> str:
    text = " ".join((look or "").split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0] + "…"


def character_looks_line(board: ComicStoryboard, *, compact: bool = False) -> str:
    if not board.characters:
        return "main comic characters in the foreground, consistent design"
    if compact:
        parts = [
            f"{c.name}: {_short_look(c.look, max_chars=80)}" for c in board.characters[:4]
        ]
        return "same characters: " + "; ".join(parts)
    parts = [f"{c.name} ({c.id}): {_short_look(c.look)}" for c in board.characters]
    return "Character sheet: " + " | ".join(parts)


def _englishish_scene(visual: str, panel_index: int) -> str:
    """Prefer Latin prompts for Flux; Cyrillic tails are often ignored."""
    scene = " ".join((visual or "").split())
    if not scene:
        return f"panel {panel_index} with the main characters acting"
    if _CYRILLIC.search(scene) and not re.search(r"[A-Za-z]{3,}", scene):
        return (
            f"panel {panel_index} story beat from the brief, characters in the foreground, "
            f"clear action (scene note was non-English)"
        )
    return scene[:220]


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


def _clip_prompt(text: str, *, limit: int = _MAX_GET_PROMPT_CHARS) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rsplit(" ", 1)[0] + "…"


def build_comic_page_prompt(board: ComicStoryboard) -> str:
    """Single-image comic page (experimental): keep short for GET URL limits."""
    n = len(board.panels)
    beats = [
        f"P{panel.index}:{_englishish_scene(panel.visual, panel.index)[:90]}"
        for panel in board.panels
    ]
    style = (board.style or "bold ink comic, flat colors").strip()[:80]
    parts = [
        f"comic book page, {page_layout_instruction(n)}",
        style,
        character_looks_line(board, compact=True),
        "different action each panel",
        " // ".join(beats),
        _FOREGROUND_CLAUSE,
        NO_TEXT_CLAUSE,
    ]
    return _clip_prompt(". ".join(p for p in parts if p))


def panel_seed(board: ComicStoryboard, panel: ComicPanel) -> int:
    return int(board.seed) + int(panel.index) * 1009


def build_panel_image_prompt(board: ComicStoryboard, panel: ComicPanel) -> str:
    """One Pollinations image per panel — Flux follows this much better than multi-grid pages."""
    scene = _englishish_scene(panel.visual, panel.index)
    style = (board.style or "clean comic book illustration, flat colors, bold outlines").strip()[
        :90
    ]
    parts = [
        f"Comic panel {panel.index}/{len(board.panels)}: {scene}",
        character_looks_line(board, compact=True),
        style,
        _FOREGROUND_CLAUSE,
        NO_TEXT_CLAUSE,
    ]
    return _clip_prompt(". ".join(p for p in parts if p))


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
        layout = _as_str(data.get("layout")) or "per_panel"
        board.layout = layout if layout in {"single_page", "per_panel"} else "per_panel"
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


STORYBOARD_SYSTEM = """You are a comic storyboard planner.
Return ONLY one JSON object (no markdown fences) with this shape:
{
  "title": "...",
  "style": "bold ink comic, flat cel shading",
  "seed": 12345,
  "characters": [{"id": "cat", "name": "Cat", "look": "orange tabby, blue scarf, green eyes, bipedal"}],
  "panels": [
    {
      "index": 1,
      "visual": "Cat waves on a metro platform, robot approaches",
      "speaker": "cat",
      "dialogue": "Hey!",
      "caption": null,
      "text_mode": "bubble"
    }
  ]
}
Rules:
- panels length 3–6 inclusive.
- Keep the user's spoken lines when they supplied dialogue (any language OK for dialogue/caption).
- EVERY panel needs non-empty dialogue OR caption. Prefer short dialogue.
- characters.look: English, ~15–40 words, distinctive colors/props (same sheet reused per panel).
- visual: MUST be English. Lead with who does what. Different action each panel. No text/letters/bubbles in visual.
- dialogue must be a STRING (not an object). speaker is a character id string.
- text_mode: "bubble" | "caption" | "both".
- style: short English art direction.
"""
