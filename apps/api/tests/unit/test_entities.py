from datetime import UTC, datetime
from uuid import uuid4

from app.domain.entities import Message, MessageRole, Session, SessionStatus


def test_assistant_message_carries_model_id() -> None:
    msg = Message(
        id=uuid4(),
        session_id=uuid4(),
        role=MessageRole.ASSISTANT,
        content="hello",
        created_at=datetime.now(UTC),
        model_id="model-b",
    )
    assert msg.role is MessageRole.ASSISTANT
    assert msg.model_id == "model-b"


def test_user_message_has_no_model_id_by_default() -> None:
    msg = Message(
        id=uuid4(),
        session_id=uuid4(),
        role=MessageRole.USER,
        content="hi",
        created_at=datetime.now(UTC),
    )
    assert msg.model_id is None


def test_session_is_anonymous_by_default() -> None:
    session = Session(
        id=uuid4(),
        access_token="opaque",
        scenario_id="default",
        status=SessionStatus.ACTIVE,
        created_at=datetime.now(UTC),
    )
    assert session.user_id is None
    assert session.status is SessionStatus.ACTIVE
