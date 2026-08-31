"""Request and response models. access_token is returned exactly once."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.entities import AUTO_MODEL

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


class MessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    model_id: str | None
    created_at: datetime


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CONTENT_BYTES)


class ProbeMessage(BaseModel):
    role: str = "user"
    content: str


class ProbeRequest(BaseModel):
    prompt: str | None = None
    messages: list[ProbeMessage] | None = None
    stream: bool = False
    model: str = AUTO_MODEL


class ProbeResponse(BaseModel):
    content: str
    model_id: str
