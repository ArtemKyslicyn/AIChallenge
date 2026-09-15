"""Day 11 — three-layer agent memory model.

Layers are stored separately; writes are always explicit (caller picks the layer).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class MemoryLayer(StrEnum):
    SHORT_TERM = "short_term"  # current dialog turns
    WORKING = "working"  # current task scratchpad
    LONG_TERM = "long_term"  # profile / decisions / knowledge


#: What belongs where (for docs + UI copy).
LAYER_PURPOSE: dict[MemoryLayer, str] = {
    MemoryLayer.SHORT_TERM: "Реплики текущего диалога (кто что сказал).",
    MemoryLayer.WORKING: "Данные активной задачи: цель, чеклист, черновики.",
    MemoryLayer.LONG_TERM: "Профиль, принятые решения, устойчивые знания.",
}


@dataclass(slots=True)
class WorkingMemory:
    goal: str = ""
    checklist: list[str] = field(default_factory=list)
    scratch: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "checklist": list(self.checklist),
            "scratch": dict(self.scratch),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> WorkingMemory:
        data = dict(raw or {})
        checklist = data.get("checklist") or []
        if not isinstance(checklist, list):
            checklist = []
        scratch = data.get("scratch") or {}
        if not isinstance(scratch, Mapping):
            scratch = {}
        return cls(
            goal=str(data.get("goal") or ""),
            checklist=[str(x) for x in checklist][:40],
            scratch={str(k): str(v) for k, v in scratch.items()},
        )


@dataclass(slots=True)
class LongTermMemory:
    profile: dict[str, str] = field(default_factory=dict)
    decisions: list[str] = field(default_factory=list)
    knowledge: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": dict(self.profile),
            "decisions": list(self.decisions),
            "knowledge": dict(self.knowledge),
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> LongTermMemory:
        data = dict(raw or {})
        profile = data.get("profile") or {}
        knowledge = data.get("knowledge") or {}
        decisions = data.get("decisions") or []
        if not isinstance(profile, Mapping):
            profile = {}
        if not isinstance(knowledge, Mapping):
            knowledge = {}
        if not isinstance(decisions, list):
            decisions = []
        return cls(
            profile={str(k): str(v) for k, v in profile.items()},
            decisions=[str(x) for x in decisions][:80],
            knowledge={str(k): str(v) for k, v in knowledge.items()},
        )


@dataclass(frozen=True, slots=True)
class MemoryWrite:
    """Explicit write: caller chooses the layer — never auto-promoted."""

    layer: MemoryLayer
    kind: str  # goal | checklist_item | scratch | profile | decision | knowledge
    key: str = ""
    value: str = ""


def apply_working_write(mem: WorkingMemory, write: MemoryWrite) -> WorkingMemory:
    if write.layer != MemoryLayer.WORKING:
        raise ValueError("working write requires layer=working")
    next_mem = WorkingMemory(
        goal=mem.goal,
        checklist=list(mem.checklist),
        scratch=dict(mem.scratch),
    )
    kind = write.kind.strip().lower()
    if kind == "goal":
        next_mem.goal = write.value.strip()[:500]
    elif kind == "checklist_item":
        item = write.value.strip()[:200]
        if item and item not in next_mem.checklist:
            next_mem.checklist.append(item)
    elif kind == "scratch":
        key = (write.key or "note").strip()[:64] or "note"
        next_mem.scratch[key] = write.value.strip()[:1000]
    else:
        raise ValueError(f"unknown working kind: {write.kind}")
    return next_mem


def apply_long_term_write(mem: LongTermMemory, write: MemoryWrite) -> LongTermMemory:
    if write.layer != MemoryLayer.LONG_TERM:
        raise ValueError("long_term write requires layer=long_term")
    next_mem = LongTermMemory(
        profile=dict(mem.profile),
        decisions=list(mem.decisions),
        knowledge=dict(mem.knowledge),
    )
    kind = write.kind.strip().lower()
    if kind == "profile":
        key = (write.key or "name").strip()[:64] or "name"
        next_mem.profile[key] = write.value.strip()[:500]
    elif kind == "decision":
        item = write.value.strip()[:400]
        if item and item not in next_mem.decisions:
            next_mem.decisions.append(item)
    elif kind == "knowledge":
        key = (write.key or "fact").strip()[:64] or "fact"
        next_mem.knowledge[key] = write.value.strip()[:1000]
    else:
        raise ValueError(f"unknown long_term kind: {write.kind}")
    return next_mem


def format_short_term_block(messages: list[Any], *, max_turns: int = 12) -> str:
    """Human-readable short-term slice (not a substitute for chat history)."""
    if not messages:
        return ""
    recent = list(messages)[-max_turns:]
    lines: list[str] = ["[краткосрочная память — текущий диалог]"]
    for m in recent:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, Mapping) else "?")
        if isinstance(m, Mapping):
            content = m.get("content")
        else:
            content = getattr(m, "content", None)
        text = " ".join(str(content or "").split())
        if len(text) > 220:
            text = text[:217] + "…"
        lines.append(f"- {role}: {text}")
    return "\n".join(lines)


def format_working_block(mem: WorkingMemory) -> str:
    if not mem.goal and not mem.checklist and not mem.scratch:
        return ""
    lines = ["[рабочая память — текущая задача]"]
    if mem.goal:
        lines.append(f"Цель: {mem.goal}")
    if mem.checklist:
        lines.append("Чеклист:")
        for item in mem.checklist:
            lines.append(f"  - {item}")
    if mem.scratch:
        lines.append("Черновики:")
        for k, v in mem.scratch.items():
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines)


def format_long_term_block(mem: LongTermMemory) -> str:
    if not mem.profile and not mem.decisions and not mem.knowledge:
        return ""
    lines = ["[долговременная память — профиль / решения / знания]"]
    if mem.profile:
        lines.append("Профиль:")
        for k, v in mem.profile.items():
            lines.append(f"  - {k}: {v}")
    if mem.decisions:
        lines.append("Решения:")
        for d in mem.decisions:
            lines.append(f"  - {d}")
    if mem.knowledge:
        lines.append("Знания:")
        for k, v in mem.knowledge.items():
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines)


def build_memory_system_extra(
    *,
    short_term_messages: list[Any] | None = None,
    working: WorkingMemory | None = None,
    long_term: LongTermMemory | None = None,
    include_short_term: bool = False,
    include_working: bool = True,
    include_long_term: bool = True,
) -> str:
    """Assemble explicit memory blocks for the agent system prompt.

    Short-term turns usually travel as chat history; the short_term *block*
    is optional (debug / demo) so layers stay visibly separate in the prompt.
    """
    parts: list[str] = []
    if include_long_term and long_term is not None:
        block = format_long_term_block(long_term)
        if block:
            parts.append(block)
    if include_working and working is not None:
        block = format_working_block(working)
        if block:
            parts.append(block)
    if include_short_term and short_term_messages is not None:
        block = format_short_term_block(short_term_messages)
        if block:
            parts.append(block)
    return "\n\n".join(parts)
