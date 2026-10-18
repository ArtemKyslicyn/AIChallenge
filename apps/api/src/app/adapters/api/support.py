"""Support desk HTTP API."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.adapters.support_json import JsonTicketStore
from app.application.support_ask import answer_support_question
from app.core.deps import Container, get_container
from app.domain.rag import NullRagClient

router = APIRouter(prefix="/support", tags=["support"])


class SupportAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    ticket_id: str | None = None
    session_snapshot: dict[str, object] | None = None


class SupportAskResponse(BaseModel):
    body: str
    escalate: bool
    model_id: str
    faq_sources: list[str]
    ticket_id: str | None = None


def _tickets() -> JsonTicketStore:
    """Prefer repo data/support; fall back to /tmp in slim Docker images."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "data" / "support"
        if candidate.is_dir() or (parent / "challenges").is_dir():
            return JsonTicketStore(candidate)
    return JsonTicketStore(Path("/tmp/aichallenge-support"))


@router.post("/ask", response_model=SupportAskResponse)
async def support_ask(
    body: SupportAskRequest,
    container: Annotated[Container, Depends(get_container)],
) -> SupportAskResponse:
    rag = getattr(container, "rag_client", None) or NullRagClient()
    answer = await answer_support_question(
        question=body.question,
        ticket_id=body.ticket_id,
        tickets=_tickets(),
        rag=rag,
        session_snapshot=body.session_snapshot,
    )
    return SupportAskResponse(
        body=answer.body,
        escalate=answer.escalate,
        model_id=answer.model_id,
        faq_sources=list(answer.faq_sources),
        ticket_id=answer.ticket.id if answer.ticket else None,
    )
