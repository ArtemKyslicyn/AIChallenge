"""Agent dialog persistence (Postgres JSONB history)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AgentDialogMessage:
    id: str
    role: str  # user | assistant
    content: str
    created_at: datetime
    model_id: str | None = None


@dataclass(slots=True)
class AgentDialog:
    id: UUID
    #: Normalized X-Visitor-Id (browser client UUID) — ownership key.
    client_visitor_id: str
    client_draft_id: str
    name: str
    system_prompt: str
    preferred_model: str
    temperature: float | None
    max_tokens: int | None
    #: Chat-aligned HMAC (client id + IP digest); refreshed each turn, not ownership.
    visitor_hash: str | None = None
    messages: list[AgentDialogMessage] = field(default_factory=list)
    #: Rolling LLM summary of messages[:summary_until_count].
    summary_text: str = ""
    summary_until_count: int = 0
    #: Sticky key-value facts for context_mode=facts.
    facts: dict[str, str] = field(default_factory=dict)
    parent_dialog_id: UUID | None = None
    branch_label: str | None = None
    forked_from_message_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
