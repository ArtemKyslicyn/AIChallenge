"""Unit tests for Day-13 task state machine."""

from __future__ import annotations

import pytest

from app.domain.agent_memory import WorkingMemory, build_memory_system_extra
from app.domain.errors import MessageValidationError
from app.domain.task_state import (
    TaskEvent,
    TaskStage,
    TaskState,
    apply_task_event,
    format_task_state_block,
    parse_task_chat_command,
)


def test_start_advance_to_done() -> None:
    s = TaskState()
    s = apply_task_event(s, TaskEvent(name="start", goal="Собрать отчёт"))
    assert s.stage == TaskStage.PLANNING
    assert s.goal == "Собрать отчёт"
    s = apply_task_event(s, TaskEvent(name="advance"))
    assert s.stage == TaskStage.EXECUTION
    s = apply_task_event(s, TaskEvent(name="advance"))
    assert s.stage == TaskStage.VALIDATION
    s = apply_task_event(s, TaskEvent(name="advance"))
    assert s.stage == TaskStage.DONE


def test_pause_at_any_stage_and_resume_keeps_stage() -> None:
    s = apply_task_event(TaskState(), TaskEvent(name="start", goal="G"))
    s = apply_task_event(s, TaskEvent(name="advance"))
    assert s.stage == TaskStage.EXECUTION
    s = apply_task_event(s, TaskEvent(name="pause"))
    assert s.paused is True
    assert "execution" in s.resume_brief
    s = apply_task_event(s, TaskEvent(name="resume"))
    assert s.paused is False
    assert s.stage == TaskStage.EXECUTION


def test_invalid_advance_from_idle() -> None:
    with pytest.raises(MessageValidationError):
        apply_task_event(TaskState(), TaskEvent(name="advance"))


def test_cannot_advance_while_paused() -> None:
    s = apply_task_event(TaskState(), TaskEvent(name="start", goal="G"))
    s = apply_task_event(s, TaskEvent(name="pause"))
    with pytest.raises(MessageValidationError):
        apply_task_event(s, TaskEvent(name="advance"))


def test_parse_directives() -> None:
    assert parse_task_chat_command("пауза").name == "pause"  # type: ignore[union-attr]
    assert parse_task_chat_command("пауза").skip_llm is True  # type: ignore[union-attr]
    assert parse_task_chat_command("продолжи").name == "resume"  # type: ignore[union-attr]
    assert parse_task_chat_command("этап дальше").name == "advance"  # type: ignore[union-attr]
    ev = parse_task_chat_command("задача: сделать демо")
    assert ev is not None and ev.name == "start" and ev.goal == "сделать демо"
    assert parse_task_chat_command("привет") is None


def test_working_memory_roundtrip_task() -> None:
    wm = WorkingMemory(goal="x", task=TaskState(stage=TaskStage.PLANNING, goal="x"))
    restored = WorkingMemory.from_mapping(wm.to_dict())
    assert restored.task.stage == TaskStage.PLANNING
    assert restored.task.goal == "x"


def test_format_block_after_working() -> None:
    wm = WorkingMemory(goal="цель", task=TaskState(stage=TaskStage.EXECUTION, step="2/3", goal="цель"))
    working = build_memory_system_extra(working=wm, include_long_term=False)
    task_block = format_task_state_block(wm.task)
    combined = f"{working}\n\n{task_block}"
    assert "рабочая память" in combined
    assert "[задача · execution]" in combined
    assert combined.index("рабочая") < combined.index("[задача")
    assert "не пересказывай" in task_block
