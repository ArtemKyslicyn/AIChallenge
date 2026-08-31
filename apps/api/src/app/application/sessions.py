"""Session use cases: creation and authorization."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from app.domain.entities import Session, SessionStatus
from app.domain.errors import ScenarioNotFoundError, SessionNotFoundError
from app.domain.ports import ScenarioRepository, SessionRepository

ACCESS_TOKEN_BYTES = 32


def new_access_token() -> str:
    """Opaque bearer token for an anonymous session."""
    return secrets.token_urlsafe(ACCESS_TOKEN_BYTES)


async def create_session(
    *,
    sessions: SessionRepository,
    scenarios: ScenarioRepository,
    scenario_id: str | None,
    token_factory: Callable[[], str] = new_access_token,
    id_factory: Callable[[], UUID] = uuid4,
    now: Callable[[], datetime],
) -> Session:
    if scenario_id:
        scenario = await scenarios.get(scenario_id)
        if scenario is None:
            raise ScenarioNotFoundError(f"Неизвестный сценарий «{scenario_id}».")
    else:
        scenario = await scenarios.get_default()

    session = Session(
        id=id_factory(),
        access_token=token_factory(),
        scenario_id=scenario.id,
        status=SessionStatus.ACTIVE,
        created_at=now(),
    )
    return await sessions.create(session)


async def authorize_session(
    *,
    sessions: SessionRepository,
    session_id: UUID,
    access_token: str | None,
) -> Session:
    """Return the session only for a matching token.

    Unknown session and wrong token raise the same error on purpose, so the
    API cannot be used to discover which session ids exist. The comparison is
    constant-time.
    """
    session = await sessions.get(session_id)
    if session is None:
        # Still burn a comparison so a missing session is not measurably faster.
        secrets.compare_digest("x" * 43, access_token or "")
        raise SessionNotFoundError("Сессия не найдена.")
    if not secrets.compare_digest(session.access_token, access_token or ""):
        raise SessionNotFoundError("Сессия не найдена.")
    return session
