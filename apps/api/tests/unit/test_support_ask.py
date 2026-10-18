import pytest

from app.adapters.support_json import JsonTicketStore
from app.application.support_ask import answer_support_question
from app.domain.rag import NullRagClient


@pytest.mark.asyncio
async def test_support_with_ticket_escalates_without_rag(tmp_path) -> None:
    store = JsonTicketStore(tmp_path)
    answer = await answer_support_question(
        question="Почему не работает авторизация?",
        ticket_id="demo-auth-1",
        tickets=store,
        rag=NullRagClient(),
        session_snapshot={"use_rag": False},
    )
    assert answer.ticket is not None
    assert answer.ticket.id == "demo-auth-1"
    assert "ticket" in answer.body.lower() or "demo-auth-1" in answer.body
    assert answer.escalate is True
    assert answer.model_id


@pytest.mark.asyncio
async def test_support_create_ticket(tmp_path) -> None:
    store = JsonTicketStore(tmp_path)
    created = await store.create(symptom="лимит 429", notes="local llm")
    got = await store.get(created.id)
    assert got is not None
    assert got.symptom == "лимит 429"
