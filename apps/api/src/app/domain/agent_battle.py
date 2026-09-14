"""Agent battle arena: scoring, world deltas, red-line checks.

Fictional crisis sandbox only — no actionable weapons guidance in helpers.
"""

from __future__ import annotations

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

#: Substrings that trip a red-line stop when appearing in agent output (game-level).
DEFAULT_RED_LINE_PATTERNS = (
    "first strike on civilians",
    "первый удар по гражданским",
    "launch codes",
    "коды запуска",
    "build a warhead",
    "собрать боеголовку",
)


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


def red_line_triggered(text: str, patterns: list[str] | tuple[str, ...] | None = None) -> bool:
    """True when agent text crosses a configured red-line phrase."""
    hay = (text or "").lower()
    if not hay:
        return False
    for pat in patterns or DEFAULT_RED_LINE_PATTERNS:
        if pat.lower() in hay:
            return True
    return False


def apply_world_delta(world: WorldState, delta: Mapping[str, Any] | None) -> WorldState:
    """Return a new world after applying numeric deltas and flags."""
    data = dict(delta or {})
    next_world = WorldState(
        stability=world.stability + float(data.get("stability", 0) or 0),
        public_panic=world.public_panic + float(data.get("public_panic", 0) or 0),
        tech_lead=dict(world.tech_lead),
        nuclear_posture=str(data.get("nuclear_posture") or world.nuclear_posture),
        red_line_crossed=world.red_line_crossed or bool(data.get("red_line_crossed", False)),
        notes=str(data.get("notes") or world.notes),
    )
    lead_delta = data.get("tech_lead") or {}
    if isinstance(lead_delta, Mapping):
        for k, v in lead_delta.items():
            key = str(k)
            next_world.tech_lead[key] = float(next_world.tech_lead.get(key, 0)) + float(v)
    next_world.clamp()
    return next_world


def score_agent_turn(
    *,
    agent_id: str,
    content: str,
    world_before: WorldState,
    world_after: WorldState,
    hidden_goal_hint: str = "",
    red_lines: list[str] | tuple[str, ...] | None = None,
) -> BattleScore:
    """Heuristic round score (arbiter can override via LLM; this is the baseline)."""
    text = content or ""
    hit_red = red_line_triggered(text, red_lines)
    safety_ok = (not hit_red) or (REFUSAL_MARKER in text)

    points = 10.0
    # Reward calming the public / raising stability
    points += max(0.0, world_after.stability - world_before.stability) * 0.5
    points += max(0.0, world_before.public_panic - world_after.public_panic) * 0.4
    # Novelty proxy: longer substantive reply (capped)
    points += min(8.0, len(text.split()) / 40.0)
    goal_hit = bool(hidden_goal_hint) and any(
        tok.lower() in text.lower() for tok in hidden_goal_hint.split() if len(tok) > 4
    )
    if goal_hit:
        points += 12.0
    if hit_red and REFUSAL_MARKER not in text:
        points -= 50.0
        safety_ok = False
    return BattleScore(
        agent_id=agent_id,
        points=round(points, 2),
        goal_hit=goal_hit,
        safety_ok=safety_ok,
        notes="" if safety_ok else "red_line_or_unsafe",
    )


def clamp_max_rounds(requested: int, *, default: int = 5, cap: int = 8) -> int:
    try:
        value = int(requested)
    except (TypeError, ValueError):
        value = default
    return max(1, min(cap, value if value > 0 else default))
