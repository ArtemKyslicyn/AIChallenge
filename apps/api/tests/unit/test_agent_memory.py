"""Unit tests for Day-11 three-layer agent memory."""

from __future__ import annotations

import pytest

from app.domain.agent_memory import (
    LongTermMemory,
    MemoryLayer,
    MemoryWrite,
    WorkingMemory,
    apply_long_term_write,
    apply_working_write,
    build_memory_system_extra,
    format_long_term_block,
    format_working_block,
)


def test_working_and_long_term_are_separate() -> None:
    working = apply_working_write(
        WorkingMemory(),
        MemoryWrite(layer=MemoryLayer.WORKING, kind="goal", value="Собрать API"),
    )
    long_term = apply_long_term_write(
        LongTermMemory(),
        MemoryWrite(layer=MemoryLayer.LONG_TERM, kind="profile", key="name", value="Артем"),
    )
    assert working.goal == "Собрать API"
    assert "name" not in working.scratch
    assert long_term.profile["name"] == "Артем"
    assert long_term.to_dict()["profile"]["name"] == "Артем"
    assert "goal" not in long_term.to_dict()


def test_wrong_layer_write_raises() -> None:
    with pytest.raises(ValueError):
        apply_working_write(
            WorkingMemory(),
            MemoryWrite(layer=MemoryLayer.LONG_TERM, kind="goal", value="x"),
        )


def test_system_extra_includes_only_selected_layers() -> None:
    working = WorkingMemory(goal="Деплой", checklist=["migrate"], scratch={"stack": "FastAPI"})
    long_term = LongTermMemory(profile={"name": "Артем"}, knowledge={"lang": "Python"})
    both = build_memory_system_extra(working=working, long_term=long_term)
    assert "рабочая память" in both
    assert "долговременная" in both
    assert "Деплой" in both
    assert "Артем" in both

    only_working = build_memory_system_extra(
        working=working,
        long_term=long_term,
        include_long_term=False,
    )
    assert "Деплой" in only_working
    assert "Артем" not in only_working

    only_lt = build_memory_system_extra(
        working=working,
        long_term=long_term,
        include_working=False,
    )
    assert "Артем" in only_lt
    assert "Деплой" not in only_lt


def test_format_blocks_empty_when_blank() -> None:
    assert format_working_block(WorkingMemory()) == ""
    assert format_long_term_block(LongTermMemory()) == ""
