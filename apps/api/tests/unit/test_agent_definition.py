"""Unit tests for AgentDefinition validation."""

from __future__ import annotations

import pytest

from app.domain.agent_definition import AgentDefinition, validate_agent_run
from app.domain.errors import MessageValidationError


def _def(**kwargs: object) -> AgentDefinition:
    base = {
        "name": "Редактор",
        "system_prompt": "Ты краткий редактор.",
        "preferred_model": "auto",
    }
    base.update(kwargs)
    return AgentDefinition(**base)  # type: ignore[arg-type]


def test_validate_happy() -> None:
    validate_agent_run(_def(), message="привет", max_message_chars=100)


def test_validate_empty_system() -> None:
    with pytest.raises(MessageValidationError, match="Инструкция"):
        validate_agent_run(_def(system_prompt="  "), message="hi", max_message_chars=100)


def test_validate_empty_message() -> None:
    with pytest.raises(MessageValidationError, match="Сообщение"):
        validate_agent_run(_def(), message=" ", max_message_chars=100)


def test_validate_oversize_system() -> None:
    with pytest.raises(MessageValidationError, match="Инструкция"):
        validate_agent_run(
            _def(system_prompt="x" * 50), message="hi", max_message_chars=20
        )
