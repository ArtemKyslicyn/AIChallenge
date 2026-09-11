"""SQLAlchemy adapter for agent workshop dialogs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import AgentDialogRow
from app.domain.agent_dialog import AgentDialog, AgentDialogMessage


def _parse_messages(raw: list[dict] | None) -> list[AgentDialogMessage]:
    out: list[AgentDialogMessage] = []
    if not raw:
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")
        mid = str(item.get("id") or "")
        if role not in ("user", "assistant") or not content or not mid:
            continue
        created_raw = item.get("created_at")
        if isinstance(created_raw, datetime):
            created_at = created_raw
        else:
            try:
                created_at = datetime.fromisoformat(str(created_raw).replace("Z", "+00:00"))
            except Exception:  # noqa: BLE001
                from datetime import UTC

                created_at = datetime.now(UTC)
        model_id = item.get("model_id")
        out.append(
            AgentDialogMessage(
                id=mid,
                role=role,
                content=content,
                created_at=created_at,
                model_id=str(model_id) if model_id else None,
            )
        )
    return out


def _dump_messages(messages: list[AgentDialogMessage]) -> list[dict]:
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "model_id": m.model_id,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


def _to_domain(row: AgentDialogRow) -> AgentDialog:
    return AgentDialog(
        id=row.id,
        client_visitor_id=row.client_visitor_id,
        visitor_hash=row.visitor_hash,
        client_draft_id=row.client_draft_id,
        name=row.name,
        system_prompt=row.system_prompt,
        preferred_model=row.preferred_model,
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        messages=_parse_messages(list(row.messages or [])),
        summary_text=getattr(row, "summary_text", "") or "",
        summary_until_count=int(getattr(row, "summary_until_count", 0) or 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SqlAlchemyAgentDialogRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, dialog_id: UUID) -> AgentDialog | None:
        row = await self._db.get(AgentDialogRow, dialog_id)
        return _to_domain(row) if row is not None else None

    async def get_by_client_draft(
        self, *, client_visitor_id: str, client_draft_id: str
    ) -> AgentDialog | None:
        stmt = select(AgentDialogRow).where(
            AgentDialogRow.client_visitor_id == client_visitor_id,
            AgentDialogRow.client_draft_id == client_draft_id,
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def save(self, dialog: AgentDialog) -> AgentDialog:
        row = await self._db.get(AgentDialogRow, dialog.id)
        if row is None:
            row = AgentDialogRow(
                id=dialog.id,
                client_visitor_id=dialog.client_visitor_id,
                visitor_hash=dialog.visitor_hash,
                client_draft_id=dialog.client_draft_id,
                name=dialog.name,
                system_prompt=dialog.system_prompt,
                preferred_model=dialog.preferred_model,
                temperature=dialog.temperature,
                max_tokens=dialog.max_tokens,
                messages=_dump_messages(dialog.messages),
                summary_text=dialog.summary_text or "",
                summary_until_count=int(dialog.summary_until_count or 0),
                created_at=dialog.created_at,
                updated_at=dialog.updated_at,
            )
            self._db.add(row)
        else:
            row.name = dialog.name
            row.system_prompt = dialog.system_prompt
            row.preferred_model = dialog.preferred_model
            row.temperature = dialog.temperature
            row.max_tokens = dialog.max_tokens
            row.visitor_hash = dialog.visitor_hash
            row.messages = _dump_messages(dialog.messages)
            row.summary_text = dialog.summary_text or ""
            row.summary_until_count = int(dialog.summary_until_count or 0)
            row.updated_at = dialog.updated_at
        await self._db.flush()
        return _to_domain(row)
