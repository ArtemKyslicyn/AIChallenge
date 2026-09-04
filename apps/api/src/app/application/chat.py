"""Chat use case: persist a user turn, stream the answer, attribute the model.

The generator yields transport-agnostic events; an adapter turns them into SSE
frames. Three things this code is careful about:

* the user message is durable before the provider is ever called;
* whatever text arrives is persisted with the model that produced it, even if
  the provider dies mid-answer or the client hangs up;
* the model is never switched mid-answer (see ModelRouter).
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from app.application.cascade import try_cheap_first
from app.application.comic import (
    STORYBOARD_SYSTEM,
    build_comic_page_prompt,
    page_image_size,
    parse_storyboard_json,
    serialize_comic_fence,
    storyboard_narration,
)
from app.application.media_tools import (
    MEDIA_TOOLS,
    SessionMediaRateLimiter,
    detect_media_intent,
    execute_media_tool,
    maybe_needs_media_tools,
    tool_calls_from_completion,
)
from app.application.sessions import authorize_session, session_title_from_message
from app.domain.cascade import CASCADE_OFF, AnswerScorer
from app.domain.entities import (
    AUTO_MODEL,
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
    MediaGenerationError,
    MediaRateLimitError,
    MessageValidationError,
    SessionClosedError,
)
from app.domain.media import COMIC_TOOL_NAME, IMAGE_TOOL_NAME, VIDEO_TOOL_NAME
from app.domain.ports import (
    ChatRouter,
    MediaGenerator,
    MediaStore,
    MessageRepository,
    RunTraceRepository,
    ScenarioRepository,
    SessionRepository,
    UnitOfWork,
)
from app.domain.tracing import (
    STATUS_ABORTED,
    STATUS_ERROR,
    STATUS_EXHAUSTED,
    STATUS_OK,
    AttemptRecord,
    RunTrace,
)

logger = logging.getLogger(__name__)

#: Appended to a persisted answer that was cut short, so a truncated reply is
#: never mistaken for a complete one on reload.
INTERRUPTED_MARKER = "\n\n[прервано]"

ERROR_INTERRUPTED = "Модель перестала отвечать. Часть ответа сохранена."
ERROR_NO_MODEL = "Сейчас нет доступной модели. Попробуйте чуть позже."
ERROR_EMPTY = "Модель вернула пустой ответ."
ERROR_GENERIC = "Не удалось получить ответ ассистента."


@dataclass(slots=True, frozen=True)
class CascadeSettings:
    """One object rather than six kwargs, so the knobs travel together.

    ``enabled`` is separate from ``cheap_models`` on purpose: an operator who
    empties the model list has misconfigured the cascade, while one who flips
    the switch has turned it off. Both end up doing nothing, but only the
    second is intentional.
    """

    enabled: bool
    cheap_models: list[str]
    timeout_seconds: float
    max_question_chars: int


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
    #: How the turn ended, mirroring the trace. Empty until it has ended at
    #: all, which is exactly the state a reader who hung up leaves behind.
    #: Read out of band by the judge, which has nothing to grade in an answer
    #: that errored, was cut off, or never found a model.
    status: str = ""
    #: User question + metrics for ops analytics (fail-open capture).
    prompt: str = ""
    latency_ms: int | None = None
    tokens_approx: int | None = None
    cost_proxy: float | None = None
    chat_mode: str | None = None
    #: Media tool outcomes for ops analytics: [{kind, ok, provider, error?}]
    media_jobs: list[dict[str, object]] = field(default_factory=list)

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
    #: off | cheap | escalated. Carried on the last frame because that is the
    #: first moment the stage is known — and the moment the rating strip
    #: appears, so the badge and the thumbs arrive together rather than the
    #: badge popping in mid-stream.
    cascade_stage: str = CASCADE_OFF


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


@dataclass(slots=True)
class ComicStartEvent:
    comic_id: str
    title: str
    panel_count: int
    characters: list[dict[str, str]]
    layout: str = "single_page"


@dataclass(slots=True)
class ComicPanelEvent:
    comic_id: str
    index: int
    status: str
    text_mode: str
    image_url: str | None = None
    speaker: str | None = None
    dialogue: str | None = None
    caption: str | None = None
    error: str | None = None


@dataclass(slots=True)
class ComicEndEvent:
    comic_id: str
    ok_count: int
    fail_count: int


ChatEvent = (
    ModelEvent
    | TokenEvent
    | MessageEndEvent
    | ErrorEvent
    | ToolStartEvent
    | ToolResultEvent
    | ComicStartEvent
    | ComicPanelEvent
    | ComicEndEvent
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
    traces: RunTraceRepository | None = None,
    cost_proxy: Mapping[str, float] | None = None,
    scorer: AnswerScorer | None = None,
    cascade: CascadeSettings | None = None,
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
    draft.prompt = text

    turns = build_llm_turns(scenario, [*history, user_message], max_history_messages)

    model = preferred_model if preferred_model is not None else scenario.preferred_model

    accumulated = draft.chunks
    resolved_model: str | None = None
    persisted = False

    # Measurement state. The clock starts before the first call to the router —
    # including the media tool round — so total_ms is what the reader waited.
    attempts: list[AttemptRecord] = []
    started = time.monotonic()
    first_token_at: float | None = None
    tool_rounds = 0
    tool_failures = 0

    # Set before the stream opens and read by save_trace, so a turn the cascade
    # never touched records "off" rather than nothing.
    cascade_stage = CASCADE_OFF
    cheap_model_id: str | None = None
    cheap_score: float | None = None

    def _elapsed_ms(until: float) -> int:
        return max(0, int((until - started) * 1000))

    async def save_trace(model_id: str | None, answer: str, status: str) -> None:
        """Record what the turn cost. Never allowed to break the stream.

        A failed write leaves the transaction poisoned, so it is rolled back —
        otherwise the next commit on this session would inherit the error.
        """
        if traces is None:
            return
        trace = RunTrace(
            id=id_factory(),
            session_id=session.id,
            message_id=assistant.id,
            visitor_hash=session.visitor_hash,
            preferred_model=model,
            resolved_model_id=model_id,
            attempts=list(attempts),
            ttft_ms=_elapsed_ms(first_token_at) if first_token_at is not None else None,
            total_ms=_elapsed_ms(time.monotonic()),
            token_count_est=max(1, len(answer) // 4) if answer else None,
            cost_proxy=(cost_proxy or {}).get(model_id) if model_id else None,
            tool_rounds=tool_rounds,
            tool_ok=(tool_failures == 0) if tool_rounds else None,
            status=status,
            created_at=now(),
            cascade_stage=cascade_stage,
            cheap_model_id=cheap_model_id,
            cheap_score=cheap_score,
        )
        try:
            await traces.save(trace)
            await uow.commit()
        except Exception:
            logger.warning(
                "run trace not saved session_id=%s message_id=%s",
                session.id,
                assistant.id,
                exc_info=True,
            )
            with contextlib.suppress(Exception):
                await uow.rollback()

    async def finalize(model_id: str | None, *, marker: str = "", status: str = STATUS_OK) -> str:
        nonlocal persisted
        answer = "".join(accumulated) + marker
        if not persisted:
            persisted = True
            await messages.update_content(assistant.id, answer, model_id)
            await uow.commit()
            draft.finished = True
            draft.status = status
            draft.latency_ms = _elapsed_ms(time.monotonic())
            draft.tokens_approx = max(1, len(answer) // 4) if answer else None
            draft.cost_proxy = (cost_proxy or {}).get(model_id) if model_id else None
            # One save point for every ending — ok, aborted, exhausted, error.
            # A reader who hangs up never reaches here, and writes no trace.
            await save_trace(model_id, answer, status)
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
                probe = await router.complete_chat(turns, preferred_model=model, tools=MEDIA_TOOLS)
                calls = tool_calls_from_completion(probe.tool_calls)
                if probe.model_id:
                    resolved_model = probe.model_id
                    draft.model_id = resolved_model
            except (LLMExhaustedError, LLMProviderError):
                calls = []
        blocks: list[str] = []
        comic_finished = False
        for call in calls[:2]:
            tool_rounds += 1
            yield ToolStartEvent(name=call.name, call_id=call.id)
            if call.name == COMIC_TOOL_NAME:
                args = call.arguments if isinstance(call.arguments, dict) else {}
                brief = str(args.get("brief") or args.get("prompt") or text).strip() or text
                try:
                    story_turns = [
                        ChatMessage(role=MessageRole.SYSTEM, content=STORYBOARD_SYSTEM),
                        ChatMessage(
                            role=MessageRole.USER,
                            content=(
                                "Build a comic storyboard JSON for this brief. "
                                "Preserve user dialogue when present.\n\n"
                                f"{brief}"
                            ),
                        ),
                    ]
                    board = None
                    plan_model: str | None = None
                    last_err: str | None = None
                    for _attempt in range(2):
                        try:
                            plan = await router.complete_chat(
                                story_turns, preferred_model=model
                            )
                            plan_model = plan.model_id or plan_model
                            board = parse_storyboard_json(plan.content)
                            break
                        except (ValueError, json.JSONDecodeError) as exc:
                            last_err = str(exc)
                            story_turns = [
                                *story_turns,
                                ChatMessage(
                                    role=MessageRole.USER,
                                    content=(
                                        "Previous output was invalid. "
                                        f"Error: {exc}. Return ONLY valid JSON."
                                    ),
                                ),
                            ]
                        except (LLMExhaustedError, LLMProviderError) as exc:
                            last_err = str(exc)
                            break
                    if board is None:
                        raise MediaGenerationError(
                            last_err or "Не удалось собрать раскадровку комикса."
                        )
                    assert media_limiter is not None
                    # One page image for the whole strip (not N Pollinations calls).
                    media_limiter.check_images(session.id, 1)
                    if plan_model:
                        resolved_model = plan_model
                        draft.model_id = resolved_model
                        yield ModelEvent(model_id=resolved_model)
                    narration = storyboard_narration(board)
                    accumulated.append(narration)
                    if first_token_at is None:
                        first_token_at = time.monotonic()
                    yield TokenEvent(text=narration)
                    yield ComicStartEvent(
                        comic_id=board.comic_id,
                        title=board.title,
                        panel_count=len(board.panels),
                        characters=[
                            {"id": c.id, "name": c.name, "look": c.look}
                            for c in board.characters
                        ],
                        layout="single_page",
                    )
                    ok_count = 0
                    fail_count = 0
                    assert media_generator is not None and media_store is not None
                    page_url: str | None = None
                    page_error: str | None = None
                    try:
                        media_limiter.check(session.id, IMAGE_TOOL_NAME)
                        width, height = page_image_size(len(board.panels))
                        artifact = await media_generator.generate_image(
                            build_comic_page_prompt(board),
                            model="flux",
                            width=width,
                            height=height,
                            seed=board.seed,
                        )
                        stored = await media_store.save(artifact)
                        media_limiter.record(session.id, IMAGE_TOOL_NAME)
                        page_url = stored.public_path
                        board.page_image_url = page_url
                        board.layout = "single_page"
                        ok_count = len(board.panels)
                        for panel in board.panels:
                            panel.image_url = page_url
                            panel.status = "ok"
                            yield ComicPanelEvent(
                                comic_id=board.comic_id,
                                index=panel.index,
                                status="ok",
                                image_url=page_url,
                                speaker=panel.speaker,
                                dialogue=panel.dialogue,
                                caption=panel.caption,
                                text_mode=panel.text_mode,
                            )
                    except (MediaGenerationError, MediaRateLimitError, OSError) as exc:
                        page_error = str(exc)[:200]
                        fail_count = len(board.panels)
                        for panel in board.panels:
                            panel.status = "error"
                            panel.error = page_error
                            yield ComicPanelEvent(
                                comic_id=board.comic_id,
                                index=panel.index,
                                status="error",
                                speaker=panel.speaker,
                                dialogue=panel.dialogue,
                                caption=panel.caption,
                                text_mode=panel.text_mode,
                                error=page_error,
                            )
                    yield ComicEndEvent(
                        comic_id=board.comic_id,
                        ok_count=ok_count,
                        fail_count=fail_count,
                    )
                    fence = serialize_comic_fence(board)
                    accumulated.append(fence)
                    # Persist fence in message content, but do not stream raw JSON to the UI.
                    if ok_count == 0:
                        tool_failures += 1
                        draft.media_jobs.append(
                            {
                                "kind": "comic",
                                "ok": False,
                                "tool": COMIC_TOOL_NAME,
                                "error": page_error or "comic page failed",
                                "panel_count": len(board.panels),
                                "ok_count": 0,
                                "fail_count": fail_count,
                                "layout": "single_page",
                            }
                        )
                        yield ToolResultEvent(
                            name=call.name,
                            call_id=call.id,
                            status="error",
                            error="Не удалось сгенерировать страницу комикса.",
                        )
                    else:
                        draft.media_jobs.append(
                            {
                                "kind": "comic",
                                "ok": True,
                                "tool": COMIC_TOOL_NAME,
                                "provider": "pollinations",
                                "panel_count": len(board.panels),
                                "ok_count": ok_count,
                                "fail_count": fail_count,
                                "layout": "single_page",
                                "images": 1,
                            }
                        )
                        yield ToolResultEvent(
                            name=call.name,
                            call_id=call.id,
                            status="ok",
                            media_url=page_url,
                            provider_label="comic-page+pollinations",
                        )
                        comic_finished = True
                except (MediaGenerationError, MediaRateLimitError) as exc:
                    tool_failures += 1
                    draft.media_jobs.append(
                        {
                            "kind": "comic",
                            "ok": False,
                            "tool": COMIC_TOOL_NAME,
                            "error": str(exc)[:200],
                        }
                    )
                    yield ToolResultEvent(
                        name=call.name,
                        call_id=call.id,
                        status="error",
                        error=str(exc),
                    )
                continue

            executed = await execute_media_tool(
                call,
                generator=media_generator,
                store=media_store,
                session_id=session.id,
                limiter=media_limiter,
            )
            if executed.error:
                tool_failures += 1
                draft.media_jobs.append(
                    {
                        "kind": "video" if call.name == VIDEO_TOOL_NAME else "image",
                        "ok": False,
                        "tool": call.name,
                        "error": str(executed.error)[:200],
                    }
                )
                yield ToolResultEvent(
                    name=call.name,
                    call_id=call.id,
                    status="error",
                    error=executed.error,
                )
            else:
                draft.media_jobs.append(
                    {
                        "kind": "video" if call.name == VIDEO_TOOL_NAME else "image",
                        "ok": True,
                        "tool": call.name,
                        "provider": executed.provider_label or "",
                    }
                )
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
            # Counts as the first token: it is the first thing the reader sees.
            first_token_at = time.monotonic()
            yield TokenEvent(text=media_prefix)

        if comic_finished:
            end_model = resolved_model or "media-tools"
            draft.model_id = end_model
            if resolved_model is None:
                yield ModelEvent(model_id=end_model)
            answer = await finalize(end_model)
            yield MessageEndEvent(
                message_id=assistant.id,
                content=answer,
                model_id=end_model,
                cascade_stage=cascade_stage,
            )
            return

    # The cheap stage runs after the tool round (media never cascades) and
    # before the first token, which is the only moment a model may still be
    # swapped. It is non-streaming by necessity: the scorer has to see the
    # whole answer, and an answer already on screen cannot be escalated.
    #
    # An explicit pin from the composer beats the automation — the same rule
    # the feedback penalty follows.
    pinned = model not in ("", AUTO_MODEL)
    if cascade is not None and cascade.enabled and scorer is not None and not pinned:
        outcome = await try_cheap_first(
            turns=turns,
            router=router,
            scorer=scorer,
            cheap_models=cascade.cheap_models,
            attempts=attempts,
            timeout_seconds=cascade.timeout_seconds,
            max_question_chars=cascade.max_question_chars,
        )
        cascade_stage = outcome.stage
        cheap_model_id = outcome.cheap_model_id
        cheap_score = outcome.cheap_score
        if outcome.accepted_text is not None and outcome.model_id is not None:
            resolved_model = outcome.model_id
            draft.model_id = resolved_model
            yield ModelEvent(model_id=resolved_model)
            accumulated.append(outcome.accepted_text)
            # One frame, not a typing impersonation: the answer is already whole.
            yield TokenEvent(text=outcome.accepted_text)
            if first_token_at is None:
                first_token_at = time.monotonic()
            answer = await finalize(resolved_model)
            yield MessageEndEvent(
                message_id=assistant.id,
                content=answer,
                model_id=resolved_model,
                cascade_stage=cascade_stage,
            )
            return

    try:
        try:
            async for chunk in router.stream_chat(turns, preferred_model=model, attempts=attempts):
                if chunk.model_id != resolved_model:
                    resolved_model = chunk.model_id
                    draft.model_id = resolved_model
                    yield ModelEvent(model_id=resolved_model)
                accumulated.append(chunk.text)
                if first_token_at is None:
                    first_token_at = time.monotonic()
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
            await finalize(exc.model_id, marker=INTERRUPTED_MARKER, status=STATUS_ABORTED)
            yield ErrorEvent(message=ERROR_INTERRUPTED)
            return
        except LLMExhaustedError:
            logger.warning("model chain exhausted session_id=%s", session.id)
            await finalize(None, status=STATUS_EXHAUSTED)
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
            await finalize(resolved_model, status=STATUS_ERROR)
            yield ErrorEvent(message=ERROR_GENERIC)
            return

        if resolved_model is None and not media_prefix:
            await finalize(None, status=STATUS_ERROR)
            yield ErrorEvent(message=ERROR_EMPTY)
            return

        # Media-only success (LLM empty) still needs a model label for history.
        end_model = resolved_model or "media-tools"
        draft.model_id = end_model
        if resolved_model is None:
            yield ModelEvent(model_id=end_model)
        answer = await finalize(end_model)
        yield MessageEndEvent(
            message_id=assistant.id,
            content=answer,
            model_id=end_model,
            cascade_stage=cascade_stage,
        )
    finally:
        # Deliberately no database write here. On a client disconnect this code
        # runs inside a task that is already being cancelled, so the await would
        # be cancelled mid-operation — which not only loses the answer but also
        # leaves the connection in a state SQLAlchemy cannot return to the pool.
        # Whatever arrived is in `draft`; saving it is the caller's job, out of
        # band and shielded from that cancellation.
        pass
