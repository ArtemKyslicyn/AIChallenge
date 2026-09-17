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
    current = parse_invariants(dialog.invariants)
    nxt, label = apply_invariant_event(current, event)
    dialog.invariants = dump_invariants(nxt)
    dialog.updated_at = datetime.now(UTC)
    saved = await dialogs.save(dialog)
    return saved, label
