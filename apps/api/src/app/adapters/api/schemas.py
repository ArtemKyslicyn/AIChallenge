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
    #: off | cheap | escalated — carried for the same reason as ``feedback``:
    #: a reload must not silently drop what the footer said about this answer.
    #: Never null; ``off`` means the cascade did not take part.
    cascade_stage: str = CASCADE_OFF


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
    #: Judge verdict 0..1, or null when this run was not judged — the sampler
    #: looks at a fraction of answers, so null is the common case.
    quality_score: float | None = None
    #: Which model gave that verdict, so two judges are never mistaken for one.
    quality_model_id: str | None = None


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


class AgentDefinitionPayload(BaseModel):
    name: str = ""
    system_prompt: str = Field(default="", max_length=MAX_CONTENT_BYTES)
    preferred_model: str = AUTO_MODEL
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=8192)


class AgentWorkshopRunRequest(BaseModel):
    definition: AgentDefinitionPayload
    message: str = Field(default="", max_length=MAX_CONTENT_BYTES)
    #: When set with a visitor id, history lives in Postgres (agent_dialogs).
    client_draft_id: str | None = Field(default=None, max_length=64)
    dialog_id: UUID | None = None
    #: Persist + continue dialog (solo). Team / progon keep false.
    persist: bool = False
    #: Context window budget for token fit (Day 8). Lab demos may pass a low value.
    context_limit: int | None = Field(default=None, ge=64, le=128_000)
    #: Day 10: mutually exclusive context mode (none|compress|sliding|facts).
    context_mode: str | None = Field(default=None, max_length=32)
    #: Day 9 compat: true without context_mode → compress.
    compress: bool = False
    recent_keep: int | None = Field(default=None, ge=0, le=40)
    summarize_every: int | None = Field(default=None, ge=2, le=100)
    #: Day 11 — inject working / long-term memory blocks into system prompt.
    include_working_memory: bool = True
    include_long_term_memory: bool = True
    #: Day 12 — expert lens id (chemist|psychologist|economist|neutral).
    expert_lens_id: str | None = Field(default=None, max_length=32)


class AgentDialogMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    model_id: str | None = None
    created_at: str


class AgentTokenTruncationResponse(BaseModel):
    applied: bool
    dropped_messages: int
    dropped_tokens_est: int
    context_limit: int
    budget: int


class AgentTokenUsageResponse(BaseModel):
    request: int
    history_before: int
    history_after: int
    completion: int
    total: int
    cost_proxy: float
    truncation: AgentTokenTruncationResponse


class AgentCompressionResponse(BaseModel):
    enabled: bool
    summary_used: bool
    summary_refreshed: bool
    summary_text: str = ""
    recent_kept: int
    covered_by_summary: int
    tokens_raw_est: int
    tokens_compressed_est: int


class AgentContextStrategyResponse(BaseModel):
    mode: str
    recent_kept: int = 0
    dropped: int = 0
    facts: dict[str, str] = Field(default_factory=dict)
    facts_updated: bool = False
    tokens_raw_est: int = 0
    tokens_strategy_est: int = 0
    summary_used: bool = False
    summary_refreshed: bool = False
    summary_text: str = ""
    covered_by_summary: int = 0


class AgentMcpCallResponse(BaseModel):
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)
    result: str


class AgentWorkshopRunResponse(BaseModel):
    content: str
    model_id: str
    dialog_id: UUID | None = None
    messages: list[AgentDialogMessageResponse] | None = None
    tokens: AgentTokenUsageResponse | None = None
    compression: AgentCompressionResponse | None = None
    context_strategy: AgentContextStrategyResponse | None = None
    invariant_conflict: bool = False
    task_skip_conflict: bool = False
    invariants: list[dict[str, object]] = Field(default_factory=list)
    mcp_calls: list[AgentMcpCallResponse] = Field(default_factory=list)


class AgentDialogResponse(BaseModel):
    id: UUID
    client_draft_id: str
    name: str
    messages: list[AgentDialogMessageResponse]
    updated_at: str
    summary_text: str = ""
    summary_until_count: int = 0
    facts: dict[str, str] = Field(default_factory=dict)
    working_memory: dict[str, object] = Field(default_factory=dict)
    invariants: list[dict[str, object]] = Field(default_factory=list)
    parent_dialog_id: UUID | None = None
    branch_label: str | None = None
    forked_from_message_id: str | None = None


class AgentDialogForkRequest(BaseModel):
    from_message_id: str = Field(min_length=1, max_length=64)
    client_draft_id: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=80)


class AgentMemorySnapshotResponse(BaseModel):
    """Three layers, stored separately (Day 11)."""

    short_term: list[AgentDialogMessageResponse] = Field(default_factory=list)
    working: dict[str, object] = Field(default_factory=dict)
    long_term: dict[str, object] = Field(default_factory=dict)


class AgentMemoryWriteRequest(BaseModel):
    """Explicit write — caller chooses the layer; nothing auto-promotes.

    Either pass layer+kind+value, or chat_text (parsed server-side).
    """

    layer: str | None = Field(default=None, description="working | long_term")
    kind: str | None = Field(
        default=None,
        description="working: goal|checklist_item|scratch; long_term: profile|decision|knowledge",
    )
    key: str = Field(default="", max_length=64)
    value: str = Field(default="", max_length=2000)
    client_draft_id: str | None = Field(default=None, max_length=64)
    #: Natural / slash command from chat — parsed into an explicit MemoryWrite.
    chat_text: str | None = Field(default=None, max_length=2000)
    #: Optional stub fields when creating a dialog for the first working write.
    dialog_name: str | None = Field(default=None, max_length=120)
    dialog_system_prompt: str | None = Field(default=None, max_length=8000)


class AgentMemoryWriteResponse(BaseModel):
    """Snapshot plus human confirmation of what was written."""

    short_term: list[AgentDialogMessageResponse] = Field(default_factory=list)
    working: dict[str, object] = Field(default_factory=dict)
    long_term: dict[str, object] = Field(default_factory=dict)
    applied: dict[str, str] = Field(default_factory=dict)
    label: str = ""


class AgentTaskEventRequest(BaseModel):
    """Server-authoritative task FSM event (Day 13)."""

    event: str = Field(
        min_length=1,
        max_length=32,
        description="start|advance|goto|set_step|set_expected|pause|resume|reset",
    )
    client_draft_id: str = Field(min_length=1, max_length=64)
    goal: str = Field(default="", max_length=500)
    step: str = Field(default="", max_length=200)
    expected_action: str = Field(default="", max_length=500)
    resume_brief: str = Field(default="", max_length=800)
    stage: str = Field(default="", max_length=32, description="Target stage for goto")
    dialog_name: str | None = Field(default=None, max_length=120)
    dialog_system_prompt: str | None = Field(default=None, max_length=8000)


class AgentTaskEventResponse(BaseModel):
    working: dict[str, object] = Field(default_factory=dict)
    task: dict[str, object] = Field(default_factory=dict)
    label: str = ""
    dialog_id: UUID | None = None


class AgentInvariantEventRequest(BaseModel):
    """Mutate dialog invariants (Day 14) — stored apart from chat turns."""

    event: str = Field(
        min_length=1,
        max_length=32,
        description="add|update|remove|seed|reset",
    )
    client_draft_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="", max_length=32)
    statement: str = Field(default="", max_length=500)
    invariant_id: str = Field(default="", max_length=64)
    triggers: list[str] = Field(default_factory=list, max_length=12)
    dialog_name: str | None = Field(default=None, max_length=120)
    dialog_system_prompt: str | None = Field(default=None, max_length=8000)


class AgentInvariantEventResponse(BaseModel):
    invariants: list[dict[str, object]] = Field(default_factory=list)
    label: str = ""
    dialog_id: UUID | None = None


class ModelCapabilitiesResponse(BaseModel):
    temperature: bool
    max_tokens: bool
    stop: bool
    reasoning: bool


class ModelCatalogItemResponse(BaseModel):
    id: str
    label: str
    capabilities: ModelCapabilitiesResponse
