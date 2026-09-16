"""Day 13 — server-authoritative task state machine.

Stages: idle → planning → execution → validation → done.
Pause is orthogonal (allowed on any non-idle stage).
LLM sees the block; it does not invent transitions.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from app.domain.errors import MessageValidationError


class TaskStage(StrEnum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTION = "execution"
    VALIDATION = "validation"
    DONE = "done"


STAGE_ORDER: tuple[TaskStage, ...] = (
    TaskStage.IDLE,
    TaskStage.PLANNING,
    TaskStage.EXECUTION,
    TaskStage.VALIDATION,
    TaskStage.DONE,
)

_ADVANCE: dict[TaskStage, TaskStage] = {
    TaskStage.PLANNING: TaskStage.EXECUTION,
    TaskStage.EXECUTION: TaskStage.VALIDATION,
    TaskStage.VALIDATION: TaskStage.DONE,
}

_DEFAULT_STEP: dict[TaskStage, str] = {
    TaskStage.PLANNING: "1/3 · согласовать план",
    TaskStage.EXECUTION: "2/3 · выполнить шаги",
    TaskStage.VALIDATION: "3/3 · проверить результат",
    TaskStage.DONE: "готово",
    TaskStage.IDLE: "",
}

_DEFAULT_EXPECTED: dict[TaskStage, str] = {
    TaskStage.PLANNING: "уточнить цель и разбить на шаги",
    TaskStage.EXECUTION: "сделать текущий шаг без повтора плана",
    TaskStage.VALIDATION: "проверить результат против цели",
    TaskStage.DONE: "задача завершена",
    TaskStage.IDLE: "",
}


@dataclass(slots=True)
class TaskState:
    stage: TaskStage = TaskStage.IDLE
    step: str = ""
    expected_action: str = ""
    paused: bool = False
    goal: str = ""
    resume_brief: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "step": self.step,
            "expected_action": self.expected_action,
            "paused": bool(self.paused),
            "goal": self.goal,
            "resume_brief": self.resume_brief,
        }

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any] | None) -> TaskState:
        data = dict(raw or {})
        stage_raw = str(data.get("stage") or TaskStage.IDLE.value).strip().lower()
        try:
            stage = TaskStage(stage_raw)
        except ValueError:
            stage = TaskStage.IDLE
        return cls(
            stage=stage,
            step=str(data.get("step") or "")[:200],
            expected_action=str(data.get("expected_action") or "")[:500],
            paused=bool(data.get("paused")),
            goal=str(data.get("goal") or "")[:500],
            resume_brief=str(data.get("resume_brief") or "")[:800],
        )


@dataclass(frozen=True, slots=True)
class TaskEvent:
    """Validated FSM event from UI or chat directive."""

    name: str  # start | advance | set_step | set_expected | pause | resume | reset
    goal: str = ""
    step: str = ""
    expected_action: str = ""
    resume_brief: str = ""
    #: When True, caller should skip LLM (deterministic ack only).
    skip_llm: bool = False


def _defaults_for(stage: TaskStage, *, goal: str = "") -> tuple[str, str]:
    step = _DEFAULT_STEP.get(stage, "")
    expected = _DEFAULT_EXPECTED.get(stage, "")
    if stage == TaskStage.PLANNING and goal:
        expected = f"уточнить план для: {goal[:120]}"
    return step, expected


def apply_task_event(state: TaskState, event: TaskEvent) -> TaskState:
    """Apply a validated event; raise MessageValidationError on illegal transitions."""
    name = (event.name or "").strip().lower()
    current = state

    if name == "start":
        goal = (event.goal or current.goal or "").strip()
        if not goal:
            raise MessageValidationError("Для старта задачи нужна цель.")
        if current.stage not in {TaskStage.IDLE, TaskStage.DONE}:
            raise MessageValidationError(
                f"Нельзя стартовать из этапа «{current.stage.value}» — сначала сброс."
            )
        step, expected = _defaults_for(TaskStage.PLANNING, goal=goal)
        return TaskState(
            stage=TaskStage.PLANNING,
            step=(event.step or step)[:200],
            expected_action=(event.expected_action or expected)[:500],
            paused=False,
            goal=goal[:500],
            resume_brief="",
        )

    if name == "advance":
        if current.paused:
            raise MessageValidationError("Задача на паузе — сначала «продолжи».")
        if current.stage == TaskStage.IDLE:
            raise MessageValidationError("Нет активной задачи — сначала «задача: …».")
        if current.stage == TaskStage.DONE:
            raise MessageValidationError("Задача уже завершена — сброс для новой.")
        nxt = _ADVANCE.get(current.stage)
        if nxt is None:
            raise MessageValidationError(f"Нельзя продвинуть этап «{current.stage.value}».")
        step, expected = _defaults_for(nxt, goal=current.goal)
        return replace(
            current,
            stage=nxt,
            step=(event.step or step)[:200],
            expected_action=(event.expected_action or expected)[:500],
            resume_brief="",
        )

    if name == "set_step":
        if current.stage == TaskStage.IDLE:
            raise MessageValidationError("Нет активной задачи.")
        step = (event.step or "").strip()
        if not step:
            raise MessageValidationError("Укажите шаг.")
        return replace(current, step=step[:200])

    if name == "set_expected":
        if current.stage == TaskStage.IDLE:
            raise MessageValidationError("Нет активной задачи.")
        expected = (event.expected_action or "").strip()
        if not expected:
            raise MessageValidationError("Укажите ожидаемое действие.")
        return replace(current, expected_action=expected[:500])

    if name == "pause":
        if current.stage in {TaskStage.IDLE, TaskStage.DONE}:
            raise MessageValidationError("Пауза недоступна на этом этапе.")
        if current.paused:
            return current
        brief = (event.resume_brief or "").strip()
        if not brief:
            bits = [
                f"этап={current.stage.value}",
                f"шаг={current.step}" if current.step else "",
                f"ожидалось={current.expected_action}" if current.expected_action else "",
                f"цель={current.goal}" if current.goal else "",
            ]
            brief = "; ".join(b for b in bits if b)[:800]
        return replace(current, paused=True, resume_brief=brief[:800])

    if name == "resume":
        if current.stage == TaskStage.IDLE:
            raise MessageValidationError("Нет задачи для продолжения.")
        if not current.paused:
            return current
        return replace(current, paused=False)

    if name == "reset":
        return TaskState()

    raise MessageValidationError(f"Неизвестное событие задачи: {name}")


def format_task_state_block(task: TaskState | None, *, just_resumed: bool = False) -> str:
    if task is None or task.stage == TaskStage.IDLE:
        return ""
    lines = [f"[задача · {task.stage.value}]"]
    if task.goal:
        lines.append(f"Цель: {task.goal}")
    if task.step:
        lines.append(f"Шаг: {task.step}")
    if task.expected_action:
        lines.append(f"Ожидается: {task.expected_action}")
    status = "на паузе" if task.paused else "активна"
    lines.append(f"Статус: {status}")
    if task.resume_brief and (task.paused or just_resumed):
        lines.append(f"Кратко для продолжения: {task.resume_brief}")
    lines.append("Правило: не пересказывай уже согласованный план; продолжай с текущего шага.")
    return "\n".join(lines)


def describe_task_event(event: TaskEvent, state: TaskState) -> str:
    name = event.name
    if name == "start":
        return f"старт · {state.stage.value} · {state.goal[:80]}"
    if name == "advance":
        return f"этап → {state.stage.value}"
    if name == "pause":
        return f"пауза · {state.stage.value}"
    if name == "resume":
        return f"продолжить · {state.stage.value}"
    if name == "reset":
        return "сброс задачи"
    if name == "set_step":
        return f"шаг · {state.step[:80]}"
    if name == "set_expected":
        return f"ожидается · {state.expected_action[:80]}"
    return name


_START_RE = re.compile(
    r"^(?:задача|task|start\s+task)\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_ADVANCE_RE = re.compile(
    r"^(?:этап\s+дальше|дальше|advance|next\s+stage)$",
    re.IGNORECASE,
)
_PAUSE_RE = re.compile(r"^(?:пауза|pause)$", re.IGNORECASE)
_RESUME_RE = re.compile(r"^(?:продолжи|продолжить|resume)$", re.IGNORECASE)
_RESET_RE = re.compile(r"^(?:сброс\s+задачи|reset\s+task)$", re.IGNORECASE)
_STEP_RE = re.compile(r"^(?:шаг|step)\s*[:：]\s*(.+)$", re.IGNORECASE | re.DOTALL)
_EXPECTED_RE = re.compile(
    r"^(?:ожидается|expected)\s*[:：]\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_task_chat_command(text: str) -> TaskEvent | None:
    """Parse chat directives into TaskEvent. None = not a task command."""
    raw = (text or "").strip()
    if not raw:
        return None
    if _PAUSE_RE.match(raw):
        return TaskEvent(name="pause", skip_llm=True)
    if _RESUME_RE.match(raw):
        return TaskEvent(name="resume", skip_llm=False)
    if _ADVANCE_RE.match(raw):
        return TaskEvent(name="advance", skip_llm=False)
    if _RESET_RE.match(raw):
        return TaskEvent(name="reset", skip_llm=True)
    m = _START_RE.match(raw)
    if m:
        return TaskEvent(name="start", goal=m.group(1).strip(), skip_llm=False)
    m = _STEP_RE.match(raw)
    if m:
        return TaskEvent(name="set_step", step=m.group(1).strip(), skip_llm=True)
    m = _EXPECTED_RE.match(raw)
    if m:
        return TaskEvent(
            name="set_expected",
            expected_action=m.group(1).strip(),
            skip_llm=True,
        )
    return None
