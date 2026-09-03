"""The vote endpoint: who may cast one, on what, and what a second one does.

Repositories are swapped for in-memory doubles, so these are HTTP-level tests
with no database — the authorization rule is the thing under test, and it is
pure application logic.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from fakes import (
    InMemoryFeedbackRepository,
    InMemoryMessageRepository,
    InMemorySessionRepository,
    RecordingUnitOfWork,
)
from fastapi.testclient import TestClient

from app.core.deps import get_feedback, get_messages, get_sessions, get_uow
from app.core.settings import Settings
from app.domain.entities import Message, MessageRole, Session, SessionStatus
from app.main import create_app

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)

SESSION_ID = UUID(int=7)
OTHER_SESSION_ID = UUID(int=8)
ANSWER_ID = UUID(int=20)
QUESTION_ID = UUID(int=21)
OTHER_ANSWER_ID = UUID(int=22)

TOKEN = "session-token"
OTHER_TOKEN = "other-session-token"

URL = f"/api/v1/messages/{ANSWER_ID}/feedback"


def message(message_id: UUID, role: MessageRole, session_id: UUID = SESSION_ID) -> Message:
    return Message(
        id=message_id,
        session_id=session_id,
        role=role,
        content="…",
        created_at=NOW,
        model_id="model-a" if role is MessageRole.ASSISTANT else None,
    )


@pytest.fixture
def messages() -> InMemoryMessageRepository:
    repo = InMemoryMessageRepository()
    repo.rows = {
        ANSWER_ID: message(ANSWER_ID, MessageRole.ASSISTANT),
        QUESTION_ID: message(QUESTION_ID, MessageRole.USER),
        OTHER_ANSWER_ID: message(OTHER_ANSWER_ID, MessageRole.ASSISTANT, OTHER_SESSION_ID),
    }
    repo.order = list(repo.rows)
    return repo


@pytest.fixture
def sessions() -> InMemorySessionRepository:
    repo = InMemorySessionRepository()
    for session_id, token in ((SESSION_ID, TOKEN), (OTHER_SESSION_ID, OTHER_TOKEN)):
        repo.rows[session_id] = Session(
            id=session_id,
            access_token=token,
            scenario_id="default",
            status=SessionStatus.ACTIVE,
            created_at=NOW,
        )
    return repo


@pytest.fixture
def votes() -> InMemoryFeedbackRepository:
    return InMemoryFeedbackRepository()


@pytest.fixture
def uow() -> RecordingUnitOfWork:
    return RecordingUnitOfWork()


@pytest.fixture
def api(
    messages: InMemoryMessageRepository,
    sessions: InMemorySessionRepository,
    votes: InMemoryFeedbackRepository,
    uow: RecordingUnitOfWork,
) -> Iterator[TestClient]:
    app = create_app(Settings(_env_file=None, use_fake_llm=True))  # type: ignore[call-arg]
    app.dependency_overrides[get_messages] = lambda: messages
    app.dependency_overrides[get_sessions] = lambda: sessions
    app.dependency_overrides[get_feedback] = lambda: votes
    app.dependency_overrides[get_uow] = lambda: uow
    with TestClient(app) as client:
        yield client


def auth(token: str = TOKEN) -> dict[str, str]:
    return {"X-Session-Token": token}


def test_a_vote_answers_with_the_message_and_the_value(api: TestClient) -> None:
    response = api.post(URL, json={"value": "up"}, headers=auth())

    assert response.status_code == 200
    assert response.json() == {"message_id": str(ANSWER_ID), "value": "up"}


def test_a_vote_is_committed_and_stored(
    api: TestClient, votes: InMemoryFeedbackRepository, uow: RecordingUnitOfWork
) -> None:
    api.post(URL, json={"value": "down"}, headers=auth())

    stored = votes.votes[ANSWER_ID]
    assert stored.value == "down"
    assert stored.session_id == SESSION_ID
    assert uow.commits == 1


def test_a_second_vote_flips_the_first_instead_of_adding_one(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    api.post(URL, json={"value": "up"}, headers=auth())
    response = api.post(URL, json={"value": "down"}, headers=auth())

    assert response.json()["value"] == "down"
    assert len(votes.votes) == 1
    assert votes.votes[ANSWER_ID].value == "down"


def test_the_visitor_header_is_stored_as_a_hash_not_as_itself(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    visitor_id = "11111111-1111-1111-1111-111111111111"
    api.post(URL, json={"value": "up"}, headers=auth() | {"X-Visitor-Id": visitor_id})

    stored_hash = votes.votes[ANSWER_ID].visitor_hash
    assert stored_hash
    assert visitor_id not in stored_hash


def test_a_vote_without_a_visitor_header_is_still_accepted(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    # The visitor id is an analytics label, never the credential.
    assert api.post(URL, json={"value": "up"}, headers=auth()).status_code == 200
    assert votes.votes[ANSWER_ID].visitor_hash is None


def test_a_wrong_token_is_a_404(api: TestClient, votes: InMemoryFeedbackRepository) -> None:
    response = api.post(URL, json={"value": "up"}, headers=auth("nope"))
    assert response.status_code == 404
    assert votes.votes == {}


def test_a_missing_token_is_a_404(api: TestClient) -> None:
    assert api.post(URL, json={"value": "up"}).status_code == 404


def test_someone_elses_message_is_a_404(api: TestClient) -> None:
    url = f"/api/v1/messages/{OTHER_ANSWER_ID}/feedback"
    assert api.post(url, json={"value": "up"}, headers=auth()).status_code == 404


def test_an_unknown_message_is_a_404(api: TestClient) -> None:
    url = f"/api/v1/messages/{UUID(int=999)}/feedback"
    assert api.post(url, json={"value": "up"}, headers=auth()).status_code == 404


def test_a_malformed_message_id_is_the_same_404(api: TestClient) -> None:
    # A 422 here would tell a prober which ids are even worth guessing.
    assert api.post("/api/v1/messages/nope/feedback", json={"value": "up"}).status_code == 404


def test_every_denial_says_exactly_the_same_thing(api: TestClient) -> None:
    bodies = [
        api.post(URL, json={"value": "up"}, headers=auth("nope")).json(),
        api.post(
            f"/api/v1/messages/{OTHER_ANSWER_ID}/feedback", json={"value": "up"}, headers=auth()
        ).json(),
        api.post(
            f"/api/v1/messages/{UUID(int=999)}/feedback", json={"value": "up"}, headers=auth()
        ).json(),
    ]
    assert bodies[0]["error"]["message"] == bodies[1]["error"]["message"]
    assert bodies[1]["error"]["message"] == bodies[2]["error"]["message"]


def test_rating_your_own_question_is_a_400_not_a_404(api: TestClient) -> None:
    # Ownership was proven, so the reason is safe to say out loud.
    response = api.post(
        f"/api/v1/messages/{QUESTION_ID}/feedback", json={"value": "up"}, headers=auth()
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "feedback_target"


@pytest.mark.parametrize("value", ["", "UP", "meh", "1", None])
def test_only_the_two_known_values_are_accepted(api: TestClient, value: object) -> None:
    assert api.post(URL, json={"value": value}, headers=auth()).status_code == 422


def test_a_rejected_vote_is_never_committed(api: TestClient, uow: RecordingUnitOfWork) -> None:
    api.post(URL, json={"value": "up"}, headers=auth("nope"))
    api.post(f"/api/v1/messages/{QUESTION_ID}/feedback", json={"value": "up"}, headers=auth())
    assert uow.commits == 0


# --- Taking a vote back -------------------------------------------------------
#
# `aria-pressed` on the thumbs promises a control that can be un-pressed, so the
# API has to offer the way back to "no opinion". Same guard as the POST, and
# idempotent: asking for a state you are already in is not an error.


def test_retracting_a_vote_removes_it_and_says_nothing_back(
    api: TestClient, votes: InMemoryFeedbackRepository, uow: RecordingUnitOfWork
) -> None:
    api.post(URL, json={"value": "up"}, headers=auth())

    response = api.delete(URL, headers=auth())

    assert response.status_code == 204
    assert response.content == b""
    assert votes.votes == {}
    assert uow.commits == 2  # the vote, then its removal


def test_retracting_when_there_is_no_vote_is_a_quiet_success(
    api: TestClient, votes: InMemoryFeedbackRepository, uow: RecordingUnitOfWork
) -> None:
    # The caller asked for "no vote on this message" and that is the state.
    assert api.delete(URL, headers=auth()).status_code == 204
    assert votes.votes == {}
    # Nothing changed, so nothing was written.
    assert uow.commits == 0


def test_retracting_twice_stays_a_204(api: TestClient) -> None:
    api.post(URL, json={"value": "down"}, headers=auth())
    assert api.delete(URL, headers=auth()).status_code == 204
    assert api.delete(URL, headers=auth()).status_code == 204


def test_a_retraction_with_a_wrong_token_is_a_404_and_keeps_the_vote(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    api.post(URL, json={"value": "up"}, headers=auth())

    assert api.delete(URL, headers=auth("nope")).status_code == 404
    assert votes.votes[ANSWER_ID].value == "up"


def test_a_retraction_without_a_token_is_a_404(api: TestClient) -> None:
    assert api.delete(URL).status_code == 404


def test_retracting_someone_elses_vote_is_a_404(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    other = f"/api/v1/messages/{OTHER_ANSWER_ID}/feedback"
    api.post(other, json={"value": "up"}, headers=auth(OTHER_TOKEN))

    assert api.delete(other, headers=auth()).status_code == 404
    assert votes.votes[OTHER_ANSWER_ID].value == "up"


def test_retracting_on_an_unknown_message_is_a_404(api: TestClient) -> None:
    url = f"/api/v1/messages/{UUID(int=999)}/feedback"
    assert api.delete(url, headers=auth()).status_code == 404


def test_a_malformed_id_is_the_same_404_on_the_way_out_too(api: TestClient) -> None:
    assert api.delete("/api/v1/messages/nope/feedback", headers=auth()).status_code == 404


def test_every_retraction_denial_says_exactly_the_same_thing(api: TestClient) -> None:
    bodies = [
        api.delete(URL, headers=auth("nope")).json(),
        api.delete(f"/api/v1/messages/{OTHER_ANSWER_ID}/feedback", headers=auth()).json(),
        api.delete(f"/api/v1/messages/{UUID(int=999)}/feedback", headers=auth()).json(),
    ]
    assert bodies[0]["error"]["message"] == bodies[1]["error"]["message"]
    assert bodies[1]["error"]["message"] == bodies[2]["error"]["message"]


def test_retracting_on_your_own_question_is_the_same_400_as_rating_it(api: TestClient) -> None:
    # Ownership was proven, so the mistake is safe to name — and the answer
    # matches the POST rather than pretending a question could hold a vote.
    response = api.delete(f"/api/v1/messages/{QUESTION_ID}/feedback", headers=auth())
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "feedback_target"


def test_a_retraction_then_a_fresh_vote_leaves_one_row(
    api: TestClient, votes: InMemoryFeedbackRepository
) -> None:
    api.post(URL, json={"value": "up"}, headers=auth())
    api.delete(URL, headers=auth())
    api.post(URL, json={"value": "down"}, headers=auth())

    assert len(votes.votes) == 1
    assert votes.votes[ANSWER_ID].value == "down"
