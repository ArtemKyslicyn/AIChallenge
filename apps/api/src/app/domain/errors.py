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
