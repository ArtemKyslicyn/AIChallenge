"""Unit tests for dialog fork."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.dialog_fork import fork_agent_dialog
from app.domain.agent_dialog import AgentDialog, AgentDialogMessage
from app.domain.errors import MessageValidationError


class _MemRepo:
    def __init__(self) -> None:
        self.by_id: dict = {}
        self.by_draft: dict = {}

    async def get(self, dialog_id):  # noqa: ANN001
        return self.by_id.get(dialog_id)

    async def get_by_client_draft(self, *, client_visitor_id, client_draft_id):  # noqa: ANN001
        return self.by_draft.get((client_visitor_id, client_draft_id))

    async def save(self, dialog: AgentDialog) -> AgentDialog:
        self.by_id[dialog.id] = dialog
        self.by_draft[(dialog.client_visitor_id, dialog.client_draft_id)] = dialog
        return dialog


@pytest.mark.asyncio
async def test_fork_copies_prefix_and_facts() -> None:
    now = datetime.now(UTC)
    msgs = [
        AgentDialogMessage(id="m0", role="user", content="u0", created_at=now),
        AgentDialogMessage(id="m1", role="assistant", content="a0", created_at=now, model_id="f"),
        AgentDialogMessage(id="m2", role="user", content="u1", created_at=now),
        AgentDialogMessage(id="m3", role="assistant", content="a1", created_at=now, model_id="f"),
    ]
    source = AgentDialog(
        id=uuid4(),
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id="root",
        name="R",
        system_prompt="sys",
        preferred_model="auto",
        temperature=0.2,
        max_tokens=100,
        messages=msgs,
        facts={"goal": "demo"},
        summary_text="sum",
        summary_until_count=2,
        created_at=now,
        updated_at=now,
    )
    repo = _MemRepo()
    await repo.save(source)
    child = await fork_agent_dialog(
        dialogs=repo,
        source=source,
        from_message_id="m1",
        client_draft_id="branch-a",
        branch_label="A",
    )
    assert len(child.messages) == 2
    assert child.messages[-1].id == "m1"
    assert child.facts == {"goal": "demo"}
    assert child.parent_dialog_id == source.id
    assert child.branch_label == "A"
    assert child.forked_from_message_id == "m1"


@pytest.mark.asyncio
async def test_fork_missing_message() -> None:
    now = datetime.now(UTC)
    source = AgentDialog(
        id=uuid4(),
        client_visitor_id="a1c4a11e-c4a1-4e07-9c06-c0a1e11e07e0",
        client_draft_id="root",
        name="R",
        system_prompt="sys",
        preferred_model="auto",
        temperature=None,
        max_tokens=None,
        messages=[],
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(MessageValidationError):
        await fork_agent_dialog(
            dialogs=_MemRepo(),
            source=source,
            from_message_id="nope",
            client_draft_id="x",
        )
