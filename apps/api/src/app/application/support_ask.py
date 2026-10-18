"""Answer a support question using FAQ hits + optional ticket context."""

from __future__ import annotations

from app.domain.rag import RagClient
from app.domain.support import SupportAnswer, TicketStore

FAQ_MIN_SCORE = 0.15


async def answer_support_question(
    *,
    question: str,
    ticket_id: str | None,
    tickets: TicketStore,
    rag: RagClient | None,
    model_id: str = "support-faq",
    session_snapshot: dict[str, object] | None = None,
) -> SupportAnswer:
    ticket = await tickets.get(ticket_id) if ticket_id else None
    faq_sources: list[str] = []
    faq_bits: list[str] = []
    best = 0.0
    if rag is not None:
        result = await rag.search(
            question,
            top_k=4,
            mode="full",
            corpus_tier="handbook",
        )
        for hit in result.hits:
            best = max(best, hit.score)
            if hit.score >= FAQ_MIN_SCORE or hit.source:
                faq_sources.append(f"{hit.title} ({hit.source})")
                faq_bits.append(hit.text[:400])

    escalate = best < FAQ_MIN_SCORE and not faq_bits
    lines: list[str] = []
    lines.append("### По вашей сессии / тикету")
    if session_snapshot:
        for key, value in session_snapshot.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- снимок сессии не передан")
    if ticket:
        lines.append(f"- ticket `{ticket.id}` status={ticket.status}")
        lines.append(f"- symptom: {ticket.symptom}")
        if ticket.notes:
            lines.append(f"- notes: {ticket.notes}")
    else:
        lines.append("- ticket не указан")

    lines.append("")
    lines.append("### Из FAQ")
    if faq_bits:
        lines.extend(faq_bits)
        lines.append("")
        lines.append("Источники: " + "; ".join(faq_sources[:6]))
    else:
        lines.append("нет в базе FAQ по этому вопросу.")

    if escalate:
        lines.append("")
        lines.append(
            "Уверенность низкая — создайте тикет или уточните симптом "
            "(не применяйте выдуманный workaround)."
        )

    return SupportAnswer(
        body="\n".join(lines),
        ticket=ticket,
        faq_sources=tuple(faq_sources),
        escalate=escalate,
        model_id=model_id,
    )
