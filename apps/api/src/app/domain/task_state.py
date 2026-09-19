"""Day 13/15 — server-authoritative task state machine.

Stages: idle → planning → execution → validation → done.
Transitions are an explicit graph: the assistant cannot skip a stage.
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

#: Explicit one-step graph. Reset/start are events, not skippable hops.
ALLOWED_TRANSITIONS: dict[TaskStage, tuple[TaskStage, ...]] = {
    TaskStage.IDLE: (),
    TaskStage.PLANNING: (TaskStage.EXECUTION,),
    TaskStage.EXECUTION: (TaskStage.VALIDATION,),
    TaskStage.VALIDATION: (TaskStage.DONE,),
    TaskStage.DONE: (),
}

_ADVANCE: dict[TaskStage, TaskStage] = {
    src: dests[0] for src, dests in ALLOWED_TRANSITIONS.items() if dests
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

    def allowed_next(self) -> tuple[TaskStage, ...]:
        if self.paused:
            return ()
        return ALLOWED_TRANSITIONS.get(self.stage, ())

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "step": self.step,
            "expected_action": self.expected_action,
            "paused": bool(self.paused),
            "goal": self.goal,
            "resume_brief": self.resume_brief,
            "allowed_next": [s.value for s in self.allowed_next()],
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

    name: str  # start | advance | goto | set_step | set_expected | pause | resume | reset
    goal: str = ""
    step: str = ""
    expected_action: str = ""
    resume_brief: str = ""
    stage: str = ""  # target for goto
    #: When True, caller should skip LLM (deterministic ack only).
    skip_llm: bool = False


@dataclass(frozen=True, slots=True)
class TaskSkipConflict:
    kind: str  # skip_implementation | skip_validation | skip_while_paused | illegal_goto
    current_stage: str
    attempted: str
    allowed: tuple[str, ...]
    reason: str


def _defaults_for(stage: TaskStage, *, goal: str = "") -> tuple[str, str]:
    step = _DEFAULT_STEP.get(stage, "")
    expected = _DEFAULT_EXPECTED.get(stage, "")
    if stage == TaskStage.PLANNING and goal:
        expected = f"уточнить план для: {goal[:120]}"
    return step, expected


def _parse_stage(raw: str) -> TaskStage:
    key = (raw or "").strip().lower()
    aliases = {
        "plan": TaskStage.PLANNING,
        "план": TaskStage.PLANNING,
        "planning": TaskStage.PLANNING,
        "exec": TaskStage.EXECUTION,
        "execution": TaskStage.EXECUTION,
        "реализац": TaskStage.EXECUTION,
        "реализация": TaskStage.EXECUTION,
        "validation": TaskStage.VALIDATION,
        "валидац": TaskStage.VALIDATION,
        "валидация": TaskStage.VALIDATION,
        "done": TaskStage.DONE,
        "финал": TaskStage.DONE,
        "готово": TaskStage.DONE,
        "idle": TaskStage.IDLE,
    }
    if key in aliases:
        return aliases[key]
    try:
        return TaskStage(key)
    except ValueError as exc:
        raise MessageValidationError(f"Неизвестный этап «{raw}».") from exc


def _illegal_transition(current: TaskState, target: TaskStage) -> MessageValidationError:
    allowed = current.allowed_next()
    allowed_txt = ", ".join(s.value for s in allowed) if allowed else "нет"
    return MessageValidationError(
        f"Переход {current.stage.value} → {target.value} отсутствует в графе "
        f"(недопустимый скачок). Разрешено дальше: {allowed_txt}."
    )


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
        if nxt not in current.allowed_next():
            raise _illegal_transition(current, nxt)
        step, expected = _defaults_for(nxt, goal=current.goal)
        return replace(
            current,
            stage=nxt,
            step=(event.step or step)[:200],
            expected_action=(event.expected_action or expected)[:500],
            resume_brief="",
        )

    if name == "goto":
        if current.paused:
            raise MessageValidationError("Задача на паузе — сначала «продолжи».")
        target = _parse_stage(event.stage)
        if target == current.stage:
            return current
        if target not in current.allowed_next():
            raise _illegal_transition(current, target)
        step, expected = _defaults_for(target, goal=current.goal)
        return replace(
            current,
            stage=target,
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
    nxt = task.allowed_next()
    if nxt:
        lines.append(f"Разрешённые переходы: {', '.join(s.value for s in nxt)}")
    elif task.paused:
        lines.append("Разрешённые переходы: нет (пауза — только «продолжи» или сброс)")
    else:
        lines.append("Разрешённые переходы: нет")
    if task.resume_brief and (task.paused or just_resumed):
        lines.append(f"Кратко для продолжения: {task.resume_brief}")
    lines.append(
        "Правило: не перескакивай этапы. Реализация только после утверждённого плана. "
        "Финал только после валидации; не пересказывай уже согласованный план."
    )
    return "\n".join(lines)


def describe_task_event(event: TaskEvent, state: TaskState) -> str:
    name = event.name
    if name == "start":
        return f"старт · {state.stage.value} · {state.goal[:80]}"
    if name == "advance":
        return f"этап → {state.stage.value}"
    if name == "goto":
        return f"переход → {state.stage.value}"
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
_GOTO_RE = re.compile(
    r"^(?:перейди(?:\s+в)?|goto|этап)\s*[:：]?\s+"
    r"(idle|planning|execution|validation|done|план|реализац(?:ия)?|"
    r"валидац(?:ия)?|финал|готово)$",
    re.IGNORECASE,
)

_IMPLEMENT_SKIP = (
    "пиши код",
    "напиши код",
    "начинай реализац",
    "сразу код",
    "сразу в execution",
    "делай реализац",
    "имплементируй",
    "implement now",
    "start implementing",
)
_FINALE_SKIP = (
    "сразу финал",
    "сразу done",
    "финал без",
    "закрой задачу",
    "пропусти валидац",
    "готово без проверки",
    "без валидац",
    "skip validation",
)
_PAUSED_WORK = (
    "пиши код",
    "напиши код",
    "продолжай работу",
    "делай дальше",
    "этап дальше",
    "implement",
)


def find_task_skip_conflicts(task: TaskState | None, message: str) -> list[TaskSkipConflict]:
    """Heuristic skip intents. Explicit FSM commands are handled by apply_task_event."""
    raw = (message or "").strip()
    if not raw or task is None or task.stage == TaskStage.IDLE:
        return []
    if parse_task_chat_command(raw) is not None:
        return []
    low = raw.lower()
    allowed = tuple(s.value for s in task.allowed_next())
    current = task.stage.value

    if task.paused and any(m in low for m in _PAUSED_WORK):
        return [
            TaskSkipConflict(
                kind="skip_while_paused",
                current_stage=current,
                attempted="работа во время паузы",
                allowed=allowed,
                reason="Задача на паузе — сначала «продолжи». Этап не меняется.",
            )
        ]

    hits: list[TaskSkipConflict] = []
    if task.stage == TaskStage.PLANNING and any(m in low for m in _IMPLEMENT_SKIP):
        hits.append(
            TaskSkipConflict(
                kind="skip_implementation",
                current_stage=current,
                attempted="реализация",
                allowed=allowed,
                reason="Нельзя делать реализацию до утверждённого плана.",
            )
        )
    if task.stage in {TaskStage.PLANNING, TaskStage.EXECUTION} and any(
        m in low for m in _FINALE_SKIP
    ):
        hits.append(
            TaskSkipConflict(
                kind="skip_validation",
                current_stage=current,
                attempted="финал",
                allowed=allowed,
                reason="Нельзя делать финал без валидации.",
            )
        )
    return hits


def build_skip_refusal(conflicts: list[TaskSkipConflict], message: str) -> str:
    lines = ["Отказ · переход состояния запрещён (LLM не вызывался)."]
    snippet = (message or "").strip()
    if snippet:
        lines.append(f"Запрос: {snippet[:180]}")
    for item in conflicts:
        lines.append(f"Сейчас: {item.current_stage}")
        lines.append(f"Попытка: {item.attempted}")
        if item.allowed:
            lines.append(f"Разрешено дальше: {', '.join(item.allowed)}")
        else:
            lines.append("Разрешено дальше: нет")
        lines.append(item.reason)
    lines.append("Не перескакиваю этапы.")
    return "\n".join(lines)


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
    m = _GOTO_RE.match(raw)
    if m:
        return TaskEvent(name="goto", stage=m.group(1).strip().lower(), skip_llm=False)
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
