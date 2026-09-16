"""Day 12 — preference profiles + expert lenses (personalization on top of memory)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(slots=True)
class PreferenceProfile:
    id: UUID
    owner_key: str
    name: str
    style: str = ""
    format: str = ""
    constraints: str = ""
    is_active: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "owner_key": self.owner_key,
            "name": self.name,
            "style": self.style,
            "format": self.format,
            "constraints": self.constraints,
            "is_active": self.is_active,
        }


@dataclass(frozen=True, slots=True)
class ExpertLens:
    id: str
    label: str
    system_addendum: str


#: Catalog lives in code (content presets — not medical product roles).
EXPERT_LENSES: tuple[ExpertLens, ...] = (
    ExpertLens(
        id="neutral",
        label="Нейтральный",
        system_addendum="",
    ),
    ExpertLens(
        id="chemist",
        label="Химик",
        system_addendum=(
            "[призма · Химик] Пиши через призму химии и веществ: реакции, свойства, "
            "осторожные аналогии с лабораторией. Без медицинских советов."
        ),
    ),
    ExpertLens(
        id="psychologist",
        label="Психолог",
        system_addendum=(
            "[призма · Психолог] Пиши через призму поведения и коммуникации: мотивы, "
            "тон, эмпатия. Без клинических диагнозов."
        ),
    ),
    ExpertLens(
        id="economist",
        label="Экономист",
        system_addendum=(
            "[призма · Экономист] Пиши через призму стимулов, издержек и компромиссов. "
            "Коротко и по делу."
        ),
    ),
)

_LENS_BY_ID = {lens.id: lens for lens in EXPERT_LENSES}


def get_expert_lens(lens_id: str | None) -> ExpertLens:
    key = (lens_id or "neutral").strip().lower() or "neutral"
    return _LENS_BY_ID.get(key, _LENS_BY_ID["neutral"])


def format_preference_block(profile: PreferenceProfile | None) -> str:
    if profile is None:
        return ""
    if not (profile.style or profile.format or profile.constraints):
        return ""
    lines = [f"[предпочтения · {profile.name or 'профиль'}]"]
    if profile.style:
        lines.append(f"Стиль: {profile.style}")
    if profile.format:
        lines.append(f"Формат: {profile.format}")
    if profile.constraints:
        lines.append(f"Ограничения: {profile.constraints}")
    return "\n".join(lines)


def format_lens_block(lens: ExpertLens | None) -> str:
    if lens is None or not lens.system_addendum.strip():
        return ""
    return lens.system_addendum.strip()


def build_personalization_extra(
    *,
    preference: PreferenceProfile | None = None,
    lens: ExpertLens | None = None,
) -> str:
    """Prefs then lens — injected after LTM identity, before working memory."""
    parts: list[str] = []
    pref = format_preference_block(preference)
    if pref:
        parts.append(pref)
    lens_block = format_lens_block(lens)
    if lens_block:
        parts.append(lens_block)
    return "\n\n".join(parts)


DEMO_PREFERENCE_SEEDS: tuple[dict[str, str], ...] = (
    {
        "name": "Кратко · JSON",
        "style": "Очень кратко, без воды",
        "format": "Ответ в JSON с полями summary и bullets",
        "constraints": "Не больше 6 ключей; без markdown-обёрток",
    },
    {
        "name": "Подробно · Markdown",
        "style": "Развёрнуто, дружелюбно",
        "format": "Markdown: заголовок + список + вывод",
        "constraints": "Можно 2–3 коротких абзаца",
    },
)
