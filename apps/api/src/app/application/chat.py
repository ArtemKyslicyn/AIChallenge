"""Chat use case: persist a user turn, stream the answer, attribute the model.

The generator yields transport-agnostic events; an adapter turns them into SSE
frames. Three things this code is careful about:

* the user message is durable before the provider is ever called;
* whatever text arrives is persisted with the model that produced it, even if
  the provider dies mid-answer or the client hangs up;
* the model is never switched mid-answer (see ModelRouter).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from app.application.sessions import authorize_session
from app.domain.entities import (
    ChatMessage,
    Message,
    MessageRole,
    Scenario,
    SessionStatus,
)
from app.domain.errors import (
    LLMExhaustedError,
    LLMProviderError,
    LLMStreamAbortedError,
    MessageValidationError,
    SessionClosedError,
)
from app.domain.ports import (
    ChatRouter,
    MessageRepository,
    ScenarioRepository,
    SessionRepository,
    UnitOfWork,
)

logger = logging.getLogger(__name__)

#: Appended to a persisted answer that was cut short, so a truncated reply is
#: never mistaken for a complete one on reload.
INTERRUPTED_MARKER = "\n\n[прервано]"

ERROR_INTERRUPTED = "Модель перестала отвечать. Часть ответа сохранена."
ERROR_NO_MODEL = "Сейчас нет доступной модели. Попробуйте чуть позже."
ERROR_EMPTY = "Модель вернула пустой ответ."
ERROR_GENERIC = "Не удалось получить ответ ассистента."


@dataclass(slots=True)
class ModelEvent:
    model_id: str


@dataclass(slots=True)
class TokenEvent:
    text: str


@dataclass(slots=True)
class MessageEndEvent:
    message_id: UUID
    content: str
    model_id: str


@dataclass(slots=True)
class ErrorEvent:
    message: str


ChatEvent = ModelEvent | TokenEvent | MessageEndEvent | ErrorEvent


def build_llm_turns(
    scenario: Scenario, history: list[Message], max_history_messages: int
) -> list[ChatMessage]:
    """System prompt plus the newest N turns.

    The full history stays in Postgres; only the slice handed to the provider
    is capped, which is what keeps a long session from growing without bound.
    """
    recent = [m for m in history if m.role is not MessageRole.SYSTEM and m.content]
    turns: list[ChatMessage] = []
    if scenario.system_prompt:
        turns.append(ChatMessage(role=MessageRole.SYSTEM, content=scenario.system_prompt))
    turns.extend(
        ChatMessage(role=m.role, content=m.content) for m in recent[-max_history_messages:]
    )
    return turns


async def send_user_message_and_stream(
    *,
    session_id: UUID,
    access_token: str | None,
    content: str,
    sessions: SessionRepository,
    messages: MessageRepository,
    scenarios: ScenarioRepository,
    router: ChatRouter,
    uow: UnitOfWork,
    now: Callable[[], datetime],
    max_message_chars: int,
    max_history_messages: int,
    id_factory: Callable[[], UUID] = uuid4,
) -> AsyncIterator[ChatEvent]:
    session = await authorize_session(
        sessions=sessions, session_id=session_id, access_token=access_token
    )
    if session.status is not SessionStatus.ACTIVE:
        raise SessionClosedError("Эта сессия больше не принимает сообщения.")

    text = content.strip()
    if not text:
        raise MessageValidationError("Сообщение не может быть пустым.")
    if len(content) > max_message_chars:
        raise MessageValidationError(f"Сообщение длиннее лимита в {max_message_chars} символов.")

    # Read config and history before writing anything, so a broken scenario
    # cannot leave orphan rows behind.
    scenario = await scenarios.get(session.scenario_id) or await scenarios.get_default()
    history = await messages.list_for_session(session.id)

    user_message = await messages.add(
        Message(
            id=id_factory(),
            session_id=session.id,
            role=MessageRole.USER,
            content=text,
            created_at=now(),
        )
    )
    assistant = await messages.add(
        Message(
            id=id_factory(),
            session_id=session.id,
            role=MessageRole.ASSISTANT,
            content="",
            created_at=now(),
        )
    )
    # Durable before the provider is called: a crash mid-answer must not lose
    # what the user typed.
    await uow.commit()

    turns = build_llm_turns(scenario, [*history, user_message], max_history_messages)

    accumulated: list[str] = []
    resolved_model: str | None = None
    persisted = False

    async def finalize(model_id: str | None, *, marker: str = "") -> str:
        nonlocal persisted
        answer = "".join(accumulated) + marker
        if not persisted:
            persisted = True
            await messages.update_content(assistant.id, answer, model_id)
            await uow.commit()
        return answer

    try:
        try:
            async for chunk in router.stream_chat(turns, preferred_model=scenario.preferred_model):
                if chunk.model_id != resolved_model:
                    resolved_model = chunk.model_id
                    yield ModelEvent(model_id=resolved_model)
                accumulated.append(chunk.text)
                yield TokenEvent(text=chunk.text)
        except LLMStreamAbortedError as exc:
            # Past the first token: keep what arrived, never splice in another model.
            logger.warning(
                "stream aborted session_id=%s message_id=%s model_id=%s",
                session.id,
                assistant.id,
                exc.model_id,
            )
            await finalize(exc.model_id, marker=INTERRUPTED_MARKER)
            yield ErrorEvent(message=ERROR_INTERRUPTED)
            return
        except LLMExhaustedError:
            logger.warning("model chain exhausted session_id=%s", session.id)
            await finalize(None)
            yield ErrorEvent(message=ERROR_NO_MODEL)
            return
        except LLMProviderError:
            logger.warning("provider failed session_id=%s", session.id)
            await finalize(resolved_model)
            yield ErrorEvent(message=ERROR_GENERIC)
            return

        if resolved_model is None:
            await finalize(None)
            yield ErrorEvent(message=ERROR_EMPTY)
            return

        answer = await finalize(resolved_model)
        yield MessageEndEvent(message_id=assistant.id, content=answer, model_id=resolved_model)
    finally:
        # Client disconnect or task cancellation lands here: persist whatever
        # arrived so the row is never left empty with a null model_id forever.
        if not persisted:
            await finalize(resolved_model, marker=INTERRUPTED_MARKER)
