"""Postgres row for one Ollama origin. The key stays in the row."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import UserLlmSourceRow
from app.domain.local_llm import LocalLlmSource


def _models(raw: str) -> tuple[str, ...]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return ()
    if not isinstance(parsed, list):
        return ()
    return tuple(str(item) for item in parsed if str(item).strip())


def _to_domain(row: UserLlmSourceRow) -> LocalLlmSource:
    return LocalLlmSource(
        user_id=row.user_id,
        name=row.name,
        base_url=row.base_url,
        api_key=row.api_key,
        enabled=row.enabled,
        models=_models(row.models_json),
        status=row.status,
        safe_error=row.safe_error,
    )


class SqlAlchemyLocalLlmSourceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_for_user(self, user_id: UUID) -> LocalLlmSource | None:
        row = await self._db.get(UserLlmSourceRow, user_id)
        return _to_domain(row) if row else None

    async def upsert(self, source: LocalLlmSource) -> None:
        row = await self._db.get(UserLlmSourceRow, source.user_id)
        payload = json.dumps(list(source.models), ensure_ascii=False)
        now = datetime.now(UTC)
        if row is None:
            self._db.add(
                UserLlmSourceRow(
                    user_id=source.user_id,
                    name=source.name,
                    base_url=source.base_url,
                    api_key=source.api_key,
                    enabled=source.enabled,
                    models_json=payload,
                    status=source.status,
                    safe_error=source.safe_error,
                    updated_at=now,
                )
            )
            return
        row.name = source.name
        row.base_url = source.base_url
        row.api_key = source.api_key
        row.enabled = source.enabled
        row.models_json = payload
        row.status = source.status
        row.safe_error = source.safe_error
        row.updated_at = now

    async def delete_for_user(self, user_id: UUID) -> None:
        await self._db.execute(delete(UserLlmSourceRow).where(UserLlmSourceRow.user_id == user_id))
