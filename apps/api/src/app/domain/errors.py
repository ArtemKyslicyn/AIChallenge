"""Domain-level errors.

Adapters map these onto transport concerns (HTTP status codes, SSE error
events). Messages must stay safe to show a client: no secrets, no provider
URLs, no stack detail.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every error the domain and application layers raise."""


class SessionNotFoundError(DomainError):
    """Unknown session, or a token that does not match it.

    Deliberately one error for both cases so the API cannot be used to
    enumerate session ids.
    """


class SessionClosedError(DomainError):
    """The session exists but no longer accepts messages."""


class ScenarioNotFoundError(DomainError):
    """Requested scenario id has no configuration."""


class MessageValidationError(DomainError):
    """User message is empty or exceeds the configured size limit."""


class ProbeDisabledError(DomainError):
    """Direct LLM probe is switched off by configuration."""


class LLMProviderError(DomainError):
    """A provider call failed. Carries just enough for the router to decide.

    ``status`` is the upstream HTTP status when there was one; ``kind`` is a
    coarse label (``quota``, ``rate_limit``, ``timeout``) for failures that
    have no status, such as a connection timeout.
    """

    def __init__(
        self,
        message: str = "LLM provider call failed.",
        *,
        status: int | None = None,
        kind: str | None = None,
        model_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.kind = kind
        self.model_id = model_id


class LLMExhaustedError(DomainError):
    """Every model in the chain is unavailable."""


class LLMStreamAbortedError(DomainError):
    """A provider died after tokens had already been streamed.

    The router never fails over at this point: continuing on another model
    would splice two different completions into one incoherent answer. The
    caller persists ``partial_text`` under ``model_id`` and ends the stream
    with an error event.
    """

    def __init__(self, *, model_id: str, partial_text: str) -> None:
        super().__init__("The model stopped responding mid-answer.")
        self.model_id = model_id
        self.partial_text = partial_text


class MessageNotFoundError(DomainError):
    """Referenced message id does not exist."""


class FeedbackTargetError(DomainError):
    """The caller may reach this message, but it is not something to rate.

    Distinct from "not found" on purpose: ownership was proven, so hiding the
    reason would only confuse a client that pointed at the wrong turn.
    """


class MediaGenerationError(DomainError):
    """External media provider failed or returned an unusable payload."""


class MediaRateLimitError(DomainError):
    """Session exceeded the configured media generation rate limit."""


class MediaNotFoundError(DomainError):
    """Unknown media id."""
