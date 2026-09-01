from fakes import (
    DEFAULT_SCENARIO,
    InMemoryScenarioRepository,
    InMemorySessionRepository,
    fixed_now,
    IdFactory,
)

from app.application.sessions import create_session, list_visitor_sessions, session_title_from_message


async def test_create_session_stores_visitor_hash() -> None:
    sessions = InMemorySessionRepository()
    scenarios = InMemoryScenarioRepository(DEFAULT_SCENARIO)
    session = await create_session(
        sessions=sessions,
        scenarios=scenarios,
        scenario_id=None,
        visitor_hash="abc123",
        ip_hash="def456",
        token_factory=lambda: "t",
        id_factory=IdFactory(),
        now=fixed_now,
    )
    assert session.visitor_hash == "abc123"
    assert session.ip_hash == "def456"


async def test_list_visitor_sessions_filters_by_hash() -> None:
    sessions = InMemorySessionRepository()
    scenarios = InMemoryScenarioRepository(DEFAULT_SCENARIO)
    mine = await create_session(
        sessions=sessions,
        scenarios=scenarios,
        scenario_id=None,
        visitor_hash="mine",
        token_factory=lambda: "a",
        id_factory=IdFactory(1),
        now=fixed_now,
    )
    await create_session(
        sessions=sessions,
        scenarios=scenarios,
        scenario_id=None,
        visitor_hash="other",
        token_factory=lambda: "b",
        id_factory=IdFactory(2),
        now=fixed_now,
    )
    rows = await list_visitor_sessions(sessions=sessions, visitor_hash="mine")
    assert len(rows) == 1
    assert rows[0].id == mine.id


def test_session_title_from_message() -> None:
    assert session_title_from_message("  Привет\nмир  ") == "Привет"
    long = "x" * 100
    assert session_title_from_message(long).endswith("…")
    assert len(session_title_from_message(long)) == 80
