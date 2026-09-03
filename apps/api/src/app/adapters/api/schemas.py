"""Request and response models. access_token is returned exactly once."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.cascade import CASCADE_OFF
from app.domain.entities import AUTO_MODEL
from app.domain.feedback import FeedbackValue

#: Hard transport cap. The configurable limit (MAX_MESSAGE_CHARS) is enforced
#: in the use case; this only stops absurd payloads before they are parsed.
MAX_CONTENT_BYTES = 100_000


class CreateSessionRequest(BaseModel):
    scenario_id: str | None = None


class SessionCreatedResponse(BaseModel):
    id: UUID
    access_token: str


class SessionResponse(BaseModel):
    id: UUID
    scenario_id: str
    status: str
    created_at: datetime
    title: str | None = None


class SessionSummaryResponse(BaseModel):
    id: UUID
    title: str | None
    created_at: datetime
    message_count: int


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    model_id: str | None
    created_at: datetime
    #: The vote already stored for this message, so a reload shows what the
    #: reader cast. ``None`` when nobody has voted on it.
    feedback: FeedbackValue | None = None


class AttemptResponse(BaseModel):
    """One model the router tried while answering, in the order it tried them."""

    model_id: str
    ok: bool
    reason: str
    ttft_ms: int | None
    error_kind: str | None


class RunTraceResponse(BaseModel):
    """Debug view of one measured turn. Deliberately carries no prompt text."""

    message_id: UUID
    resolved_model_id: str | None
    status: str
    ttft_ms: int | None
    total_ms: int | None
    attempts: list[AttemptResponse]
    created_at: datetime
    #: off | cheap | escalated — who answered, and whether a cheap try failed
    #: first. ``off`` is the normal single-model path.
    cascade_stage: str = CASCADE_OFF
    cheap_model_id: str | None = None
    cheap_score: float | None = None


class SessionTracesResponse(BaseModel):
    traces: list[RunTraceResponse]


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CONTENT_BYTES)
    #: Pin a model for this reply; ``None`` keeps the scenario default.
    model: str | None = None


class ProbeMessage(BaseModel):
    role: str = "user"
    content: str


class ProbeRequest(BaseModel):
    prompt: str | None = None
    messages: list[ProbeMessage] | None = None
    stream: bool = False
    model: str = AUTO_MODEL
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)
    stop: list[str] | None = None
    prompt_format: bool = False
    prompt_length: bool = False
    prompt_stop: bool = False
    reasoning: bool = False


class ProbeResponse(BaseModel):
    content: str
    model_id: str


class ModelCapabilitiesResponse(BaseModel):
    temperature: bool
    max_tokens: bool
    stop: bool
    reasoning: bool


class ModelCatalogItemResponse(BaseModel):
    id: str
    label: str
    capabilities: ModelCapabilitiesResponse
