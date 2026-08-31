"""Pure domain entities.

No FastAPI, SQLAlchemy, or httpx imports are allowed in this package.
Naming stays product-agnostic: no role- or industry-specific nouns.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

#: Sentinel for ``Scenario.preferred_model``: let the router pick from the chain.
AUTO_MODEL = "auto"


class SessionStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(slots=True)
class Session:
    id: UUID
    access_token: str
    scenario_id: str
    status: SessionStatus
    created_at: datetime
    user_id: UUID | None = None


@dataclass(slots=True)
class Message:
    id: UUID
    session_id: UUID
    role: MessageRole
    content: str
    created_at: datetime
    #: Model that actually produced the answer, after routing and failover.
    #: Required for persisted assistant replies, ``None`` for user/system rows.
    model_id: str | None = None


@dataclass(slots=True)
class Scenario:
    id: str
    system_prompt: str
    preferred_model: str  # "auto" or an explicit model id


@dataclass(slots=True)
class ChatMessage:
    """One turn handed to an LLM provider — decoupled from persistence."""

    role: MessageRole
    content: str


@dataclass(slots=True)
class TokenChunk:
    text: str
    model_id: str


@dataclass(slots=True)
class CompletionResult:
    content: str
    model_id: str
