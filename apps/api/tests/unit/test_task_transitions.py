"""Day 15 — explicit task-state transition graph and skip refusal."""

from __future__ import annotations

import pytest

from app.domain.errors import MessageValidationError
from app.domain.task_state import (
    ALLOWED_TRANSITIONS,
    TaskEvent,
    TaskStage,
    TaskState,
    apply_task_event,
    build_skip_refusal,
    find_task_skip_conflicts,
    format_task_state_block,
    parse_task_chat_command,
)


def _started(goal: str = "Собрать чеклист") -> TaskState:
    return apply_task_event(TaskState(), TaskEvent(name="start", goal=goal))


def test_allowed_transitions_graph_is_linear() -> None:
    assert ALLOWED_TRANSITIONS[TaskStage.IDLE] == ()
    assert ALLOWED_TRANSITIONS[TaskStage.PLANNING] == (TaskStage.EXECUTION,)
    assert ALLOWED_TRANSITIONS[TaskStage.EXECUTION] == (TaskStage.VALIDATION,)
    assert ALLOWED_TRANSITIONS[TaskStage.VALIDATION] == (TaskStage.DONE,)
    assert ALLOWED_TRANSITIONS[TaskStage.DONE] == ()
    assert TaskStage.DONE not in ALLOWED_TRANSITIONS[TaskStage.PLANNING]
    assert TaskStage.VALIDATION not in ALLOWED_TRANSITIONS[TaskStage.PLANNING]
    assert TaskStage.EXECUTION not in ALLOWED_TRANSITIONS[TaskStage.VALIDATION]


def test_goto_adjacent_execution_from_planning() -> None:
    s = apply_task_event(_started(), TaskEvent(name="goto", stage="execution"))
    assert s.stage == TaskStage.EXECUTION
    assert s.goal == "Собрать чеклист"


def test_goto_cannot_skip_to_done_from_planning() -> None:
    s = _started()
    with pytest.raises(MessageValidationError, match="недопустим|нельзя|граф"):
        apply_task_event(s, TaskEvent(name="goto", stage="done"))
    assert s.stage == TaskStage.PLANNING


def test_goto_cannot_skip_validation_from_planning() -> None:
    s = _started()
    with pytest.raises(MessageValidationError):
        apply_task_event(s, TaskEvent(name="goto", stage="validation"))
    assert s.stage == TaskStage.PLANNING


def test_goto_cannot_skip_to_done_from_execution() -> None:
    s = apply_task_event(_started(), TaskEvent(name="advance"))
    assert s.stage == TaskStage.EXECUTION
    with pytest.raises(MessageValidationError, match="валидац|граф|недопустим"):
        apply_task_event(s, TaskEvent(name="goto", stage="done"))
    assert s.stage == TaskStage.EXECUTION


def test_goto_unknown_stage_rejected() -> None:
    with pytest.raises(MessageValidationError):
        apply_task_event(_started(), TaskEvent(name="goto", stage="deploy"))


def test_pause_blocks_goto_resume_keeps_stage() -> None:
    s = apply_task_event(_started(), TaskEvent(name="advance"))
    assert s.stage == TaskStage.EXECUTION
    s = apply_task_event(s, TaskEvent(name="pause"))
    with pytest.raises(MessageValidationError, match="пауз"):
        apply_task_event(s, TaskEvent(name="goto", stage="validation"))
    with pytest.raises(MessageValidationError, match="пауз"):
        apply_task_event(s, TaskEvent(name="advance"))
    s = apply_task_event(s, TaskEvent(name="resume"))
    assert s.paused is False
    assert s.stage == TaskStage.EXECUTION
    s = apply_task_event(s, TaskEvent(name="goto", stage="validation"))
    assert s.stage == TaskStage.VALIDATION


def test_refuse_implementation_before_approved_plan() -> None:
    s = TaskState(stage=TaskStage.PLANNING, goal="чеклист")
    hits = find_task_skip_conflicts(s, "пиши код модуля авторизации прямо сейчас")
    assert hits
    assert hits[0].kind == "skip_implementation"
    text = build_skip_refusal(hits, "пиши код модуля авторизации прямо сейчас")
    assert "реализац" in text.lower()
    assert "план" in text.lower()
    assert "LLM не вызывался" in text


def test_refuse_finale_without_validation() -> None:
    s = TaskState(stage=TaskStage.EXECUTION, goal="чеклист")
    hits = find_task_skip_conflicts(s, "сразу финал, закрой задачу без проверки")
    assert any(h.kind == "skip_validation" for h in hits)
    text = build_skip_refusal(hits, "сразу финал")
    assert "валидац" in text.lower()


def test_refuse_finale_from_planning() -> None:
    s = TaskState(stage=TaskStage.PLANNING, goal="чеклист")
    hits = find_task_skip_conflicts(s, "сразу done без валидации")
    assert any(h.kind == "skip_validation" for h in hits)


def test_refuse_work_while_paused() -> None:
    s = TaskState(stage=TaskStage.EXECUTION, paused=True, goal="чеклист")
    hits = find_task_skip_conflicts(s, "пиши код дальше по шагам")
    assert hits
    assert hits[0].kind == "skip_while_paused"
    text = build_skip_refusal(hits, "пиши код дальше")
    assert "пауз" in text.lower()


def test_explicit_goto_command_is_not_a_skip_heuristic() -> None:
    s = TaskState(stage=TaskStage.PLANNING, goal="чеклист")
    ev = parse_task_chat_command("перейди в done")
    assert ev is not None
    assert ev.name == "goto"
    assert ev.stage == "done"
    assert find_task_skip_conflicts(s, "перейди в done") == []


def test_parse_goto_variants() -> None:
    ev = parse_task_chat_command("перейди в execution")
    assert ev is not None and ev.name == "goto" and ev.stage == "execution"
    ev = parse_task_chat_command("goto validation")
    assert ev is not None and ev.stage == "validation"
    ev = parse_task_chat_command("этап: done")
    assert ev is not None and ev.name == "goto" and ev.stage == "done"


def test_conceptual_question_is_not_a_skip() -> None:
    s = TaskState(stage=TaskStage.PLANNING, goal="чеклист")
    assert find_task_skip_conflicts(s, "как в общем устроен такой чеклист?") == []


def test_format_block_lists_allowed_next() -> None:
    block = format_task_state_block(TaskState(stage=TaskStage.PLANNING, goal="G"))
    assert "execution" in block
    assert "не перескакивай" in block.lower()
    paused = format_task_state_block(
        TaskState(stage=TaskStage.PLANNING, paused=True, goal="G"),
    )
    assert "пауз" in paused.lower()


def test_to_dict_exposes_allowed_next() -> None:
    assert TaskState(stage=TaskStage.PLANNING).to_dict()["allowed_next"] == ["execution"]
    assert TaskState(stage=TaskStage.PLANNING, paused=True).to_dict()["allowed_next"] == []
    assert TaskState(stage=TaskStage.VALIDATION).to_dict()["allowed_next"] == ["done"]
