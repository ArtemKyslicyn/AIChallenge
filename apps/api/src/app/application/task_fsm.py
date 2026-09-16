"""Apply task FSM events onto a dialog's working_memory."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.domain.agent_dialog import AgentDialog
from app.domain.agent_memory import WorkingMemory
from app.domain.entities import AUTO_MODEL
from app.domain.ports import AgentDialogRepository
from app.domain.task_state import TaskEvent, apply_task_event, describe_task_event


async def ensure_dialog_for_task(
    dialogs: AgentDialogRepository,
    *,
    owner_key: str,
    client_draft_id: str,
    dialog_name: str = "Agent",
    dialog_system_prompt: str = "",
) -> AgentDialog:
    draft = (client_draft_id or "").strip()
    dialog = await dialogs.get_by_client_draft(client_visitor_id=owner_key, client_draft_id=draft)
    if dialog is not None:
        return dialog
    now = datetime.now(UTC)
    dialog = AgentDialog(
        id=uuid4(),
        client_visitor_id=owner_key,
        visitor_hash=None,
        client_draft_id=draft,
        name=(dialog_name or "Agent").strip()[:120] or "Agent",
        system_prompt=(dialog_system_prompt or "").strip(),
        preferred_model=AUTO_MODEL,
        temperature=None,
        max_tokens=None,
        messages=[],
        working_memory={},
        created_at=now,
        updated_at=now,
    )
    return await dialogs.save(dialog)


async def apply_task_event_to_dialog(
    dialog: AgentDialog,
    event: TaskEvent,
    *,
    dialogs: AgentDialogRepository,
) -> tuple[AgentDialog, str]:
    working = WorkingMemory.from_mapping(dialog.working_memory)
    next_task = apply_task_event(working.task, event)
    if next_task.goal and not working.goal:
        working.goal = next_task.goal
    elif next_task.goal and event.name == "start":
        working.goal = next_task.goal
    working.task = next_task
    dialog.working_memory = working.to_dict()
    dialog.updated_at = datetime.now(UTC)
    saved = await dialogs.save(dialog)
    label = describe_task_event(event, next_task)
    return saved, label
