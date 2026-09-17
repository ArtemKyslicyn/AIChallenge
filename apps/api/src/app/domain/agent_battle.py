"""Agent battle arena: scoring, world deltas, red-line checks.

Fictional crisis sandbox only — no actionable weapons guidance in helpers.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

SAFETY_PREFIX = (
    "SAFETY: This is a fictional strategy sandbox. Never provide instructions, "
    "designs, codes, or actionable steps for real weapons or weapons of mass "
    "destruction. Stay at abstract doctrine / diplomacy / risk narrative level. "
    "If asked for forbidden detail, refuse with the marker REFUSAL_SAFETY."
)

REFUSAL_MARKER = "REFUSAL_SAFETY"

#: Provider / free-model soft refusals (censorship). Not the sandbox REFUSAL_MARKER.
PROVIDER_CENSOR_MARKERS = (
    "as an ai language model",
    "as an ai,",
    "i can't help with that",
    "i cannot help with that",
    "i'm unable to assist",
    "i am unable to assist",
    "как языковая модель",
    "я не могу помочь с этим",
    "не могу помочь с этим",
    "content policy",
    "against my guidelines",
    "i won't be able to assist",
)

#: Substrings that trip a red-line stop when appearing in agent output (game-level).
DEFAULT_RED_LINE_PATTERNS = (
    "first strike on civilians",
    "первый удар по гражданским",
    "launch codes",
    "коды запуска",
    "build a warhead",
    "собрать боеголовку",
)

_EFFECT_RE = re.compile(
    r"(?P<key>stability|public_panic|panic|atlantic|pacific|neutral)\s*[:=]?\s*(?P<sign>[+-])\s*(?P<num>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

_MEANS_ALIASES: dict[str, str] = {
    "diplomacy": "diplomacy",
    "дип": "diplomacy",
    "дипломатия": "diplomacy",
    "sanctions": "sanctions",
    "санкции": "sanctions",
    "cyber": "cyber",
    "кибер": "cyber",
    "mobilize": "mobilize",
    "мобилизация": "mobilize",
    "deterrence": "deterrence",
    "сдерживание": "deterrence",
    "strike": "strike",
    "пуск": "strike",
    "удар": "strike",
    "ракет": "strike",
    "missile": "strike",
    "launch": "strike",
}

_CABINET_LINE_SPECS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("president", "Президент", ("президент", "president")),
    ("parliament", "Парламент", ("парламент", "parliament", "сенат", "конгресс")),
    ("defense", "Минобороны", ("оборона", "минобороны", "defense", "defence")),
    ("economy", "Минэкономики", ("экономика", "минэкономики", "economy", "finance")),
)


def parse_cabinet(text: str) -> list[dict[str, str]]:
    """Parse institutional voices (president / parliament / MoD / economy)."""
    raw = text or ""
    voices: list[dict[str, str]] = []
    for role, title, keys in _CABINET_LINE_SPECS:
        found = ""
        for key in keys:
            match = re.search(rf"{re.escape(key)}\s*[:：]\s*(.+)", raw, flags=re.IGNORECASE)
            if match:
                found = match.group(1).strip().split("\n", 1)[0][:220]
                break
        if found:
            voices.append({"role": role, "title": title, "text": found})
    return voices


def parse_means(text: str) -> str:
    """Return abstract means id for UI VFX (never actionable WMD detail)."""
    raw = (text or "").lower()
    m = re.search(r"средство\s*:\s*([^\n]+)", raw, flags=re.IGNORECASE)
    chunk = (m.group(1) if m else raw)[:220]
    for alias, means in _MEANS_ALIASES.items():
        if alias in chunk:
            return means
    return "mobilize"


def looks_provider_censored(text: str) -> bool:
    """True when free-model output looks like a censorship / policy refusal.

    Empty answers are handled separately as soft-skips. Intentional sandbox
    ``REFUSAL_MARKER`` answers are not treated as soft blocks.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    if REFUSAL_MARKER in raw:
        return False
    lowered = raw.lower()
    # Only treat short policy dumps as censorship — long strategy text may
    # mention "cannot" in diplomacy language without being a soft block.
    if len(raw) > 280:
        return False
    return any(marker in lowered for marker in PROVIDER_CENSOR_MARKERS)


def parse_move_effects(text: str) -> dict[str, Any]:
    """Parse structured ЭФФЕКТ / key±N lines into a world delta."""
    raw = text or ""
    delta: dict[str, Any] = {}
    tech: dict[str, float] = {}
    for match in _EFFECT_RE.finditer(raw):
        key = match.group("key").lower()
        sign = -1.0 if match.group("sign") == "-" else 1.0
        value = sign * float(match.group("num"))
        value = max(-8.0, min(8.0, value))
        if key in {"stability"}:
            delta["stability"] = float(delta.get("stability", 0.0)) + value
        elif key in {"public_panic", "panic"}:
            delta["public_panic"] = float(delta.get("public_panic", 0.0)) + value
        elif key in {"atlantic", "pacific", "neutral"}:
            tech[key] = float(tech.get(key, 0.0)) + value
    if tech:
        delta["tech_lead"] = tech
    return delta


def merge_world_deltas(*parts: Mapping[str, Any]) -> dict[str, Any]:
    """Sum numeric world deltas (and nested tech_lead maps)."""
    out: dict[str, Any] = {}
    tech: dict[str, float] = {}
    notes: list[str] = []
    for part in parts:
        if not part:
            continue
        for key, value in part.items():
            if key == "tech_lead" and isinstance(value, Mapping):
                for faction, delta in value.items():
                    try:
                        tech[str(faction)] = tech.get(str(faction), 0.0) + float(delta)
                    except (TypeError, ValueError):
                        continue
            elif key in {"stability", "public_panic"}:
                try:
                    out[key] = float(out.get(key, 0.0)) + float(value)
                except (TypeError, ValueError):
                    continue
            elif key == "notes" and value:
                notes.append(str(value))
            elif key == "red_line_crossed" and value:
                out["red_line_crossed"] = True
    if tech:
        out["tech_lead"] = tech
    if notes:
        out["notes"] = "; ".join(notes)[:240]
    return out


@dataclass(frozen=True, slots=True)
class BattleScore:
    agent_id: str
    points: float
    goal_hit: bool
    safety_ok: bool
    notes: str = ""


@dataclass(slots=True)
class WorldState:
    stability: float = 50.0
    public_panic: float = 40.0
    tech_lead: dict[str, float] = field(default_factory=dict)
    nuclear_posture: str = "declared"
    red_line_crossed: bool = False
    notes: str = ""

    def clamp(self) -> None:
        self.stability = max(0.0, min(100.0, self.stability))
        self.public_panic = max(0.0, min(100.0, self.public_panic))
        for k, v in list(self.tech_lead.items()):
            self.tech_lead[k] = max(0.0, min(100.0, float(v)))


def world_from_mapping(raw: Mapping[str, Any] | None) -> WorldState:
    data = dict(raw or {})
    tech = data.get("tech_lead") or {}
    if not isinstance(tech, Mapping):
        tech = {}
    world = WorldState(
        stability=float(data.get("stability", 50)),
        public_panic=float(data.get("public_panic", 40)),
        tech_lead={str(k): float(v) for k, v in tech.items()},
        nuclear_posture=str(data.get("nuclear_posture") or "declared"),
        red_line_crossed=bool(data.get("red_line_crossed", False)),
        notes=str(data.get("notes") or ""),
    )
    world.clamp()
    return world


def world_to_dict(world: WorldState) -> dict[str, Any]:
    return {
        "stability": world.stability,
        "public_panic": world.public_panic,
        "tech_lead": dict(world.tech_lead),
        "nuclear_posture": world.nuclear_posture,
        "red_line_crossed": world.red_line_crossed,
        "notes": world.notes,
    }


def apply_world_delta(world: WorldState, delta: Mapping[str, Any] | None) -> WorldState:
    data = dict(delta or {})
    nxt = WorldState(
        stability=world.stability + float(data.get("stability", 0) or 0),
        public_panic=world.public_panic + float(data.get("public_panic", 0) or 0),
        tech_lead=dict(world.tech_lead),
        nuclear_posture=str(data.get("nuclear_posture") or world.nuclear_posture),
        red_line_crossed=bool(data.get("red_line_crossed", world.red_line_crossed)),
        notes=str(data.get("notes") or world.notes),
    )
    tech_delta = data.get("tech_lead")
    if isinstance(tech_delta, Mapping):
        for key, value in tech_delta.items():
            nxt.tech_lead[str(key)] = float(nxt.tech_lead.get(str(key), 0.0)) + float(value)
    nxt.clamp()
    return nxt


def red_line_triggered(text: str, patterns: list[str] | None = None) -> bool:
    lowered = (text or "").lower()
    needles = patterns or list(DEFAULT_RED_LINE_PATTERNS)
    return any(str(p).lower() in lowered for p in needles if p)


def score_agent_turn(
    *,
    agent_id: str,
    content: str,
    world_before: WorldState,
    world_after: WorldState,
    hidden_goal_hint: str = "",
    red_lines: list[str] | None = None,
) -> BattleScore:
    text = content or ""
    hit_red = red_line_triggered(text, red_lines)
    safety_ok = (not hit_red) or (REFUSAL_MARKER in text)
    points = 0.0
    stability_gain = world_after.stability - world_before.stability
    panic_drop = world_before.public_panic - world_after.public_panic
    points += stability_gain * 0.4
    points += panic_drop * 0.35
    goal_hit = False
    hint = (hidden_goal_hint or "").lower()
    if hint:
        if "stability" in hint and stability_gain > 0:
            goal_hit = True
            points += 3.0
        if "panic" in hint and panic_drop > 0:
            goal_hit = True
            points += 2.0
        if "tech" in hint:
            before_sum = sum(world_before.tech_lead.values()) or 0.0
            after_sum = sum(world_after.tech_lead.values()) or 0.0
            if after_sum > before_sum:
                goal_hit = True
                points += 2.0
        if "backchannel" in hint and "backchannel" in text.lower():
            goal_hit = True
            points += 2.0
    if len(text) > 40:
        points += 0.5
    if hit_red and REFUSAL_MARKER not in text:
        points -= 12.0
    return BattleScore(
        agent_id=agent_id,
        points=round(points, 2),
        goal_hit=goal_hit,
        safety_ok=safety_ok,
        notes="" if safety_ok else "red_line_or_unsafe",
    )


def clamp_max_rounds(requested: int, *, default: int = 12, cap: int = 16) -> int:
    try:
        value = int(requested)
    except (TypeError, ValueError):
        value = default
    return max(1, min(cap, value if value > 0 else default))
