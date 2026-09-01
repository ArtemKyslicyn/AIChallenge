"""In-memory doubles for the repository ports, shared by the use-case tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.domain.entities import Message, MessageRole, Scenario, Session, SessionSummary
from app.domain.errors import MessageNotFoundError, ScenarioNotFoundError

FIXED_NOW = datetime(2026, 8, 31, 12, 0, 0, tzinfo=UTC)


def fixed_now() -> datetime:
    return FIXED_NOW


def uuid_sequence(prefix: int = 1) -> IdFactory:
    return IdFactory(prefix)


class IdFactory:
    """Deterministic UUIDs so assertions can name the ids they expect."""

    def __init__(self, prefix: int = 1) -> None:
        self._n = 0
        self._prefix = prefix

    def __call__(self) -> UUID:
        self._n += 1
        return UUID(int=self._prefix * 1000 + self._n)


class InMemorySessionRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, Session] = {}

    async def create(self, session: Session) -> Session:
        self.rows[session.id] = session
        return session

    async def get(self, session_id: UUID) -> Session | None:
        return self.rows.get(session_id)

    async def list_for_visitor(self, visitor_hash: str, *, limit: int = 50) -> list[SessionSummary]:
        matches = [
            s
            for s in self.rows.values()
            if s.visitor_hash == visitor_hash
        ]
        matches.sort(key=lambda s: s.created_at, reverse=True)
        return [
            SessionSummary(
                id=s.id,
                title=s.title,
                created_at=s.created_at,
                message_count=0,
            )
            for s in matches[:limit]
        ]

    async def set_title_if_empty(self, session_id: UUID, title: str) -> None:
        row = self.rows.get(session_id)
        if row is None or row.title:
            return
        row.title = title[:120]


class InMemoryMessageRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, Message] = {}
        self.order: list[UUID] = []

    async def add(self, message: Message) -> Message:
        self.rows[message.id] = message
        self.order.append(message.id)
        return message

    async def list_for_session(self, session_id: UUID) -> list[Message]:
        return [self.rows[i] for i in self.order if self.rows[i].session_id == session_id]

    async def update_content(self, message_id: UUID, content: str, model_id: str | None) -> Message:
        row = self.rows.get(message_id)
        if row is None:
            raise MessageNotFoundError(str(message_id))
        row.content = content
        row.model_id = model_id
        return row

    async def get(self, message_id: UUID) -> Message | None:
        return self.rows.get(message_id)


class InMemoryScenarioRepository:
    def __init__(self, *scenarios: Scenario, default_id: str = "default") -> None:
        self.rows = {s.id: s for s in scenarios}
        self._default_id = default_id

    async def get(self, scenario_id: str) -> Scenario | None:
        return self.rows.get(scenario_id)

    async def get_default(self) -> Scenario:
        scenario = self.rows.get(self._default_id)
        if scenario is None:
            raise ScenarioNotFoundError(self._default_id)
        return scenario


class RecordingUnitOfWork:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


DEFAULT_SCENARIO = Scenario(
    id="default", system_prompt="You are a helpful assistant.", preferred_model="auto"
)
