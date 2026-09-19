"""Apply invariant events onto a dialog's dedicated invariants column."""

from __future__ import annotations

from datetime import UTC, datetime

from app.application.task_fsm import ensure_dialog_for_task
from app.domain.agent_dialog import AgentDialog
from app.domain.invariants import (
    InvariantEvent,
    apply_invariant_event,
    dump_invariants,
    parse_invariants,
)
from app.domain.ports import AgentDialogRepository

ensure_dialog_for_invariants = ensure_dialog_for_task


async def apply_invariant_event_to_dialog(
    dialog: AgentDialog,
    event: InvariantEvent,
    *,
    dialogs: AgentDialogRepository,
) -> tuple[AgentDialog, str]:
    return await apply_invariant_events_to_dialog(dialog, [event], dialogs=dialogs)


async def apply_invariant_events_to_dialog(
    dialog: AgentDialog,
    events: list[InvariantEvent],
    *,
    dialogs: AgentDialogRepository,
) -> tuple[AgentDialog, str]:
    current = parse_invariants(dialog.invariants)
    labels: list[str] = []
    for event in events:
        current, label = apply_invariant_event(current, event)
        labels.append(label)
    dialog.invariants = dump_invariants(current)
    dialog.updated_at = datetime.now(UTC)
    saved = await dialogs.save(dialog)
    return saved, "; ".join(labels)
