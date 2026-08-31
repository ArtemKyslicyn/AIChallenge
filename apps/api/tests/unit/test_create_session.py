import pytest
from fakes import (
    DEFAULT_SCENARIO,
    FIXED_NOW,
    IdFactory,
    InMemoryScenarioRepository,
    InMemorySessionRepository,
    fixed_now,
)

from app.application.sessions import authorize_session, create_session, new_access_token
from app.domain.entities import Scenario, SessionStatus
from app.domain.errors import ScenarioNotFoundError, SessionNotFoundError

OTHER = Scenario(id="onboarding", system_prompt="Ask about goals.", preferred_model="model-b")


def _deps() -> tuple[InMemorySessionRepository, InMemoryScenarioRepository]:
    return InMemorySessionRepository(), InMemoryScenarioRepository(DEFAULT_SCENARIO, OTHER)


async def test_creates_active_session_with_default_scenario() -> None:
    sessions, scenarios = _deps()
    session = await create_session(
        sessions=sessions,
        scenarios=scenarios,
        scenario_id=None,
        token_factory=lambda: "token-1",
        id_factory=IdFactory(),
        now=fixed_now,
    )
    assert session.scenario_id == "default"
    assert session.status is SessionStatus.ACTIVE
    assert session.access_token == "token-1"
    assert session.created_at == FIXED_NOW
    assert session.user_id is None
    assert sessions.rows[session.id] == session


async def test_uses_requested_scenario() -> None:
    sessions, scenarios = _deps()
    session = await create_session(
        sessions=sessions,
        scenarios=scenarios,
        scenario_id="onboarding",
        token_factory=lambda: "t",
        id_factory=IdFactory(),
        now=fixed_now,
    )
    assert session.scenario_id == "onboarding"


async def test_unknown_scenario_is_rejected() -> None:
    sessions, scenarios = _deps()
    with pytest.raises(ScenarioNotFoundError):
        await create_session(
            sessions=sessions,
            scenarios=scenarios,
            scenario_id="nope",
            token_factory=lambda: "t",
            id_factory=IdFactory(),
            now=fixed_now,
        )
    assert sessions.rows == {}


def test_default_token_is_long_and_url_safe() -> None:
    token = new_access_token()
    assert len(token) >= 32
    assert token.isascii() and "/" not in token and "+" not in token
    assert new_access_token() != token


async def test_authorize_session_accepts_matching_token() -> None:
    sessions, scenarios = _deps()
    session = await create_session(
        sessions=sessions,
        scenarios=scenarios,
        scenario_id=None,
        token_factory=lambda: "secret-token",
        id_factory=IdFactory(),
        now=fixed_now,
    )
    got = await authorize_session(
        sessions=sessions, session_id=session.id, access_token="secret-token"
    )
    assert got.id == session.id


@pytest.mark.parametrize("token", ["wrong", "", None])
async def test_authorize_session_rejects_bad_token(token: str | None) -> None:
    sessions, scenarios = _deps()
    session = await create_session(
        sessions=sessions,
        scenarios=scenarios,
        scenario_id=None,
        token_factory=lambda: "secret-token",
        id_factory=IdFactory(),
        now=fixed_now,
    )
    with pytest.raises(SessionNotFoundError):
        await authorize_session(sessions=sessions, session_id=session.id, access_token=token)


async def test_authorize_session_hides_unknown_session_behind_same_error() -> None:
    sessions, _ = _deps()
    with pytest.raises(SessionNotFoundError):
        await authorize_session(
            sessions=sessions, session_id=IdFactory()(), access_token="whatever"
        )
