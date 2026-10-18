"""JSON TicketStore under data/support/."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from app.domain.support import SupportTicket


class JsonTicketStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "tickets.json"
        if not self.path.is_file():
            self.path.write_text(
                json.dumps(
                    {
                        "tickets": [
                            {
                                "id": "demo-auth-1",
                                "status": "open",
                                "symptom": "не работает авторизация / сессия",
                                "notes": "use_rag=false; guest",
                            },
                            {
                                "id": "demo-rag-2",
                                "status": "open",
                                "symptom": "база не отвечает",
                                "notes": "rag toggle off",
                            },
                        ]
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

    def _load(self) -> list[dict[str, str]]:
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rows = data.get("tickets") or []
        return [r for r in rows if isinstance(r, dict)]

    def _save(self, rows: list[dict[str, str]]) -> None:
        self.path.write_text(
            json.dumps({"tickets": rows}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    async def get(self, ticket_id: str) -> SupportTicket | None:
        for row in self._load():
            if str(row.get("id")) == ticket_id:
                return SupportTicket(
                    id=str(row["id"]),
                    status=str(row.get("status") or "open"),
                    symptom=str(row.get("symptom") or ""),
                    notes=str(row.get("notes") or ""),
                )
        return None

    async def search(self, query: str, *, limit: int = 10) -> tuple[SupportTicket, ...]:
        q = query.strip().lower()
        out: list[SupportTicket] = []
        for row in self._load():
            blob = f"{row.get('id')} {row.get('symptom')} {row.get('notes')}".lower()
            if not q or q in blob:
                out.append(
                    SupportTicket(
                        id=str(row["id"]),
                        status=str(row.get("status") or "open"),
                        symptom=str(row.get("symptom") or ""),
                        notes=str(row.get("notes") or ""),
                    )
                )
            if len(out) >= limit:
                break
        return tuple(out)

    async def create(self, *, symptom: str, notes: str = "") -> SupportTicket:
        rows = self._load()
        ticket = SupportTicket(
            id=f"t-{uuid.uuid4().hex[:8]}",
            status="open",
            symptom=symptom.strip(),
            notes=notes.strip(),
        )
        rows.append(
            {
                "id": ticket.id,
                "status": ticket.status,
                "symptom": ticket.symptom,
                "notes": ticket.notes,
            }
        )
        self._save(rows)
        return ticket
