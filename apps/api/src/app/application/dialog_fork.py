"""Fork an agent dialog at a checkpoint message into a new draft/dialog."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.agent_dialog import AgentDialog, AgentDialogMessage
from app.domain.errors import MessageValidationError
from app.domain.ports import AgentDialogRepository


async def fork_agent_dialog(
    *,
    dialogs: AgentDialogRepository,
    source: AgentDialog,
    from_message_id: str,
    client_draft_id: str,
    branch_label: str | None = None,
) -> AgentDialog:
    draft_key = (client_draft_id or "").strip()
    if not draft_key:
        raise MessageValidationError("client_draft_id обязателен для ветки.")
    if len(draft_key) > 64:
        raise MessageValidationError("client_draft_id слишком длинный.")
    mid = (from_message_id or "").strip()
    if not mid:
        raise MessageValidationError("from_message_id обязателен.")

    existing = await dialogs.get_by_client_draft(
        client_visitor_id=source.client_visitor_id, client_draft_id=draft_key
    )
    if existing is not None:
        raise MessageValidationError("Диалог с таким client_draft_id уже есть.")

    idx = next((i for i, m in enumerate(source.messages) if m.id == mid), None)
    if idx is None:
        raise MessageValidationError("Сообщение checkpoint не найдено в диалоге.")

    prefix: list[AgentDialogMessage] = list(source.messages[: idx + 1])
    now = datetime.now(UTC)
    label = (branch_label or "").strip()[:80] or None
    child = AgentDialog(
        id=uuid4(),
        client_visitor_id=source.client_visitor_id,
        visitor_hash=source.visitor_hash,
        client_draft_id=draft_key,
        name=source.name,
        system_prompt=source.system_prompt,
        preferred_model=source.preferred_model,
        temperature=source.temperature,
        max_tokens=source.max_tokens,
        messages=prefix,
        summary_text=source.summary_text or "",
        summary_until_count=min(int(source.summary_until_count or 0), len(prefix)),
        facts=dict(source.facts or {}),
        parent_dialog_id=source.id,
        branch_label=label,
        forked_from_message_id=mid,
        created_at=now,
        updated_at=now,
    )
    return await dialogs.save(child)
