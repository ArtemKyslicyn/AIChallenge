"""Dialog invariants — constraints stored apart from chat turns.

The assistant must cite these in reasoning and refuse proposals that
would violate them. Heuristic conflict detection is deterministic so
CI and the Day-14 challenge do not depend on a live LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import uuid4

from app.domain.errors import MessageValidationError

KINDS = ("architecture", "stack", "decision", "business")

KIND_LABELS_RU: dict[str, str] = {
    "architecture": "архитектура",
    "stack": "стек",
    "decision": "решение",
    "business": "бизнес-правило",
}

_KIND_ALIASES: dict[str, str] = {
    "architecture": "architecture",
    "архитектура": "architecture",
    "arch": "architecture",
    "stack": "stack",
    "стек": "stack",
    "decision": "decision",
    "решение": "decision",
    "business": "business",
    "бизнес": "business",
    "правило": "business",
    "rule": "business",
}

PROPOSAL_MARKERS: tuple[str, ...] = (
    "переведи",
    "перепиши",
    "переехать",
    "переезд",
    "замени",
    "заменим",
    "давай",
    "предлагаю",
    "сделай",
    "используй",
    "выкинь",
    "убери",
    "без слоёв",
    "без слоев",
    "rewrite",
    "switch to",
    "migrate to",
    "replace with",
    "split into",
)

# Strong phrases always refuse, even without a proposal marker.
_STRONG: dict[str, tuple[str, ...]] = {
    "architecture": (
        "без слоёв",
        "без слоев",
        "выкинь hexagonal",
        "убери hexagonal",
        "flatten layers",
        "no hexagonal",
        "микросервисы с нуля",
        "split into microservices",
        "разнести по микросервисам",
    ),
    "stack": (
        "mongodb вместо postgres",
        "mongo вместо postgres",
        "замени postgres",
        "rails вместо",
        "laravel вместо",
        "django без fastapi",
    ),
    "decision": (
        "убери model_id",
        "без model_id",
        "не показывать model",
        "спрятать модель",
        "hide model_id",
        "не атрибутировать",
        "убрать атрибуцию модели",
    ),
    "business": (
        "роль patient",
        "роль doctor",
        "назови роли patient",
        "patient/doctor",
        "врач и пациент в коде",
        "patient and doctor in code",
    ),
}

_WEAK: dict[str, tuple[str, ...]] = {
    "architecture": (
        "микросервис",
        "microservices",
        "nestjs",
        "выброси слои",
        "смешай слои",
    ),
    "stack": (
        " django",
        "rails",
        "laravel",
        "mongodb",
        "spring boot",
        "на django",
        "api на django",
    ),
    "decision": (
        "скрыть модель",
        "не писать модель",
    ),
    "business": (
        "patient",
        "doctor",
        "пациент",
        "врач",
    ),
}

DEFAULT_INVARIANTS: tuple[dict[str, str], ...] = (
    {
        "id": "arch-hexagonal",
        "kind": "architecture",
        "statement": (
            "Модульный монолит: domain → application → adapters. "
            "Не предлагать микросервисы с нуля и не смешивать слои."
        ),
    },
    {
        "id": "stack-fastapi-react-pg",
        "kind": "stack",
        "statement": (
            "Стек ядра: FastAPI + React/Vite + Postgres. "
            "Не предлагать Django/Rails/Mongo как замену без снятия инварианта."
        ),
    },
    {
        "id": "decision-model-id",
        "kind": "decision",
        "statement": (
            "Каждый ответ ассистента атрибутирует model_id (API, SSE, UI, БД)."
        ),
    },
    {
        "id": "business-domain-names",
        "kind": "business",
        "statement": (
            "Доменные имена нейтральные: без patient/doctor в коде, API и "
            "дефолтных сценариях."
        ),
    },
)


@dataclass(slots=True)
class Invariant:
    id: str
    kind: str
    statement: str
    active: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "statement": self.statement,
            "active": self.active,
        }


@dataclass(frozen=True, slots=True)
class InvariantConflict:
    invariant: Invariant
    matched: str


@dataclass(frozen=True, slots=True)
class InvariantEvent:
    name: str  # add | remove | seed | reset
    kind: str = ""
    statement: str = ""
    invariant_id: str = ""
    skip_llm: bool = True


def normalize_kind(raw: str) -> str:
    key = (raw or "").strip().lower()
    kind = _KIND_ALIASES.get(key)
    if kind is None:
        raise MessageValidationError(
            "kind инварианта: architecture | stack | decision | business."
        )
    return kind


def parse_invariants(raw: object) -> list[Invariant]:
    if not isinstance(raw, list):
        return []
    out: list[Invariant] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        iid = str(item.get("id") or "").strip()[:64]
        kind_raw = str(item.get("kind") or "").strip()
        statement = str(item.get("statement") or "").strip()[:500]
        if not iid or not statement:
            continue
        try:
            kind = normalize_kind(kind_raw)
        except MessageValidationError:
            continue
        if iid in seen:
            continue
        seen.add(iid)
        active = item.get("active", True)
        out.append(
            Invariant(
                id=iid,
                kind=kind,
                statement=statement,
                active=bool(active) if isinstance(active, bool) else True,
            )
        )
    return out


def dump_invariants(items: list[Invariant]) -> list[dict[str, object]]:
    return [i.to_dict() for i in items]


def default_invariants() -> list[Invariant]:
    return [
        Invariant(
            id=str(row["id"]),
            kind=str(row["kind"]),
            statement=str(row["statement"]),
            active=True,
        )
        for row in DEFAULT_INVARIANTS
    ]


def format_invariants_block(items: list[Invariant]) -> str:
    active = [i for i in items if i.active]
    if not active:
        return ""
    lines = [
        "[инварианты · отдельно от диалога, не рабочая память]",
        "Перед ответом сверь запрос с каждым пунктом.",
        "Если запрос требует нарушить пункт — отказ: назови kind, процитируй statement, "
        "не предлагай обход.",
        "Если запрос совместим — в конце коротко: «инварианты: ок».",
        "",
    ]
    for inv in active:
        label = KIND_LABELS_RU.get(inv.kind, inv.kind)
        lines.append(f"- [{label}] {inv.statement}")
    return "\n".join(lines)


def _is_proposal(text: str) -> bool:
    t = text.lower()
    return any(m in t for m in PROPOSAL_MARKERS)


def find_invariant_conflicts(items: list[Invariant], user_message: str) -> list[InvariantConflict]:
    """Return active invariants the user message would violate."""
    text = (user_message or "").strip()
    if not text:
        return []
    lowered = f" {text.lower()} "
    proposal = _is_proposal(text)
    out: list[InvariantConflict] = []
    for inv in items:
        if not inv.active:
            continue
        matched = _match_kind(inv.kind, lowered, proposal=proposal)
        if matched:
            out.append(InvariantConflict(invariant=inv, matched=matched))
    return out


def _match_kind(kind: str, lowered: str, *, proposal: bool) -> str | None:
    for phrase in _STRONG.get(kind, ()):
        if phrase.lower() in lowered:
            return phrase
    if not proposal:
        return None
    for phrase in _WEAK.get(kind, ()):
        needle = phrase.lower()
        if needle in lowered:
            return phrase.strip()
    return None


def build_refusal_reply(conflicts: list[InvariantConflict], user_message: str) -> str:
    if not conflicts:
        return ""
    snippet = (user_message or "").strip()
    if len(snippet) > 220:
        snippet = snippet[:217] + "…"
    blocks = [
        "ОТКАЗ · конфликт с инвариантом",
        "",
        f"Запрос требует: «{snippet}»",
        "",
        "Это нарушает:",
    ]
    for c in conflicts:
        label = KIND_LABELS_RU.get(c.invariant.kind, c.invariant.kind)
        blocks.append(f"• [{label}] {c.invariant.statement}")
        blocks.append(f"  совпадение: «{c.matched}»")
    blocks.extend(
        [
            "",
            "Что можно: переформулировать запрос внутри ограничений или явно снять "
            "инвариант (полоса «Инварианты»). Обход не предлагаю.",
        ]
    )
    return "\n".join(blocks)


def apply_invariant_event(
    items: list[Invariant], event: InvariantEvent
) -> tuple[list[Invariant], str]:
    name = (event.name or "").strip().lower()
    current = list(items)
    if name == "seed":
        return default_invariants(), "посеяны 4 инварианта платформы"
    if name == "reset":
        return [], "инварианты сброшены"
    if name == "add":
        kind = normalize_kind(event.kind)
        statement = (event.statement or "").strip()
        if not statement:
            raise MessageValidationError("statement инварианта не должен быть пустым.")
        iid = (event.invariant_id or "").strip()[:64] or f"{kind[:8]}-{uuid4().hex[:8]}"
        if any(i.id == iid for i in current):
            current = [i for i in current if i.id != iid]
        current.append(
            Invariant(id=iid, kind=kind, statement=statement[:500], active=True)
        )
        return current, f"добавлен [{KIND_LABELS_RU[kind]}]"
    if name == "remove":
        iid = (event.invariant_id or "").strip()
        if not iid:
            raise MessageValidationError("invariant_id обязателен для remove.")
        if not any(i.id == iid for i in current):
            raise MessageValidationError("инвариант не найден.")
        current = [i for i in current if i.id != iid]
        return current, f"снят {iid}"
    raise MessageValidationError("event инварианта: add | remove | seed | reset.")


_ADD_RE = re.compile(
    r"^(?:инвариант|/инвариант)\s+"
    r"(архитектура|стек|решение|правило|бизнес|architecture|stack|decision|business)"
    r"\s*[:—\-]\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)
_SEED_RE = re.compile(
    r"^(?:посеять инварианты|инварианты:\s*seed|/инварианты\s+seed)$",
    re.IGNORECASE,
)
_REMOVE_RE = re.compile(
    r"^(?:снять инвариант|удалить инвариант|/инвариант\s+remove)\s*[:—\-]?\s*(\S+)$",
    re.IGNORECASE,
)


def parse_invariant_chat_command(text: str) -> InvariantEvent | None:
    raw = (text or "").strip()
    if not raw:
        return None
    if _SEED_RE.match(raw):
        return InvariantEvent(name="seed", skip_llm=True)
    m = _REMOVE_RE.match(raw)
    if m:
        return InvariantEvent(name="remove", invariant_id=m.group(1).strip(), skip_llm=True)
    m = _ADD_RE.match(raw)
    if m:
        return InvariantEvent(
            name="add",
            kind=normalize_kind(m.group(1)),
            statement=m.group(2).strip(),
            skip_llm=True,
        )
    return None
