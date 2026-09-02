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
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.application.media_tools import (
    MEDIA_TOOLS,
    SessionMediaRateLimiter,
    detect_media_intent,
    execute_media_tool,
    maybe_needs_media_tools,
    tool_calls_from_completion,
)
from app.application.sessions import authorize_session, session_title_from_message
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
    MediaGenerator,
    MediaStore,
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
class ReplyDraft:
    """Live state of the answer, readable by whoever drives the generator.

    A cancelled request task cannot finish its own database write: the await in
    a ``finally`` block is cancelled along with everything else. So the caller
    gets the state and is responsible for saving it out of band when the reader
    hangs up. ``finished`` says the answer was already stored here.
    """

    message_id: UUID | None = None
    chunks: list[str] = field(default_factory=list)
    model_id: str | None = None
    finished: bool = False

    @property
    def text(self) -> str:
        return "".join(self.chunks)


def interrupted_answer(draft: ReplyDraft) -> str:
    return draft.text + INTERRUPTED_MARKER


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


@dataclass(slots=True)
class ToolStartEvent:
    name: str
    call_id: str


@dataclass(slots=True)
class ToolResultEvent:
    name: str
    call_id: str
    status: str
    media_url: str | None = None
    provider_label: str | None = None
    error: str | None = None


ChatEvent = (
    ModelEvent | TokenEvent | MessageEndEvent | ErrorEvent | ToolStartEvent | ToolResultEvent
)


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
    draft: ReplyDraft | None = None,
    preferred_model: str | None = None,
    media_tools_enabled: bool = False,
    media_generator: MediaGenerator | None = None,
    media_store: MediaStore | None = None,
    media_limiter: SessionMediaRateLimiter | None = None,
) -> AsyncIterator[ChatEvent]:
    draft = draft if draft is not None else ReplyDraft()
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
    await sessions.set_title_if_empty(session.id, session_title_from_message(text))
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

    draft.message_id = assistant.id

    turns = build_llm_turns(scenario, [*history, user_message], max_history_messages)

    model = preferred_model if preferred_model is not None else scenario.preferred_model

    accumulated = draft.chunks
    resolved_model: str | None = None
    persisted = False

    async def finalize(model_id: str | None, *, marker: str = "") -> str:
        nonlocal persisted
        answer = "".join(accumulated) + marker
        if not persisted:
            persisted = True
            await messages.update_content(assistant.id, answer, model_id)
            await uow.commit()
            draft.finished = True
        return answer

    media_prefix = ""
    if (
        media_tools_enabled
        and media_generator is not None
        and media_store is not None
        and media_limiter is not None
        and maybe_needs_media_tools(text)
    ):
        calls = detect_media_intent(text)
        if not calls:
            try:
                probe = await router.complete_chat(
                    turns, preferred_model=model, tools=MEDIA_TOOLS
                )
                calls = tool_calls_from_completion(probe.tool_calls)
                if probe.model_id:
                    resolved_model = probe.model_id
                    draft.model_id = resolved_model
            except (LLMExhaustedError, LLMProviderError):
                calls = []
        blocks: list[str] = []
        for call in calls[:2]:
            yield ToolStartEvent(name=call.name, call_id=call.id)
            executed = await execute_media_tool(
                call,
                generator=media_generator,
                store=media_store,
                session_id=session.id,
                limiter=media_limiter,
            )
            if executed.error:
                yield ToolResultEvent(
                    name=call.name,
                    call_id=call.id,
                    status="error",
                    error=executed.error,
                )
            else:
                yield ToolResultEvent(
                    name=call.name,
                    call_id=call.id,
                    status="ok",
                    media_url=executed.media_url,
                    provider_label=executed.provider_label,
                )
                if executed.markdown:
                    blocks.append(executed.markdown)
        if blocks:
            media_prefix = "\n\n".join(blocks) + "\n\n"
            accumulated.append(media_prefix)
            yield TokenEvent(text=media_prefix)

    try:
        try:
            async for chunk in router.stream_chat(turns, preferred_model=model):
                if chunk.model_id != resolved_model:
                    resolved_model = chunk.model_id
                    draft.model_id = resolved_model
                    yield ModelEvent(model_id=resolved_model)
                accumulated.append(chunk.text)
                yield TokenEvent(text=chunk.text)
        except LLMStreamAbortedError as exc:
            draft.model_id = exc.model_id
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
        except LLMProviderError as exc:
            logger.warning(
                "provider failed session_id=%s status=%s kind=%s model_id=%s",
                session.id,
                exc.status,
                exc.kind,
                exc.model_id,
            )
            await finalize(resolved_model)
            yield ErrorEvent(message=ERROR_GENERIC)
            return

        if resolved_model is None and not media_prefix:
            await finalize(None)
            yield ErrorEvent(message=ERROR_EMPTY)
            return

        # Media-only success (LLM empty) still needs a model label for history.
        end_model = resolved_model or "media-tools"
        draft.model_id = end_model
        if resolved_model is None:
            yield ModelEvent(model_id=end_model)
        answer = await finalize(end_model)
        yield MessageEndEvent(message_id=assistant.id, content=answer, model_id=end_model)
    finally:
        # Deliberately no database write here. On a client disconnect this code
        # runs inside a task that is already being cancelled, so the await would
        # be cancelled mid-operation — which not only loses the answer but also
        # leaves the connection in a state SQLAlchemy cannot return to the pool.
        # Whatever arrived is in `draft`; saving it is the caller's job, out of
        # band and shielded from that cancellation.
        pass
