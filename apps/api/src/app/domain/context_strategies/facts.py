"""Sticky facts formatting and merge helpers."""

from __future__ import annotations

import json
import re

FACTS_PREFIX = "Известные факты диалога:\n"


def format_facts_block(facts: dict[str, str]) -> str:
    if not facts:
        return ""
    lines = [FACTS_PREFIX.rstrip()]
    for key in sorted(facts.keys()):
        val = (facts.get(key) or "").strip()
        if not val:
            continue
        lines.append(f"- {key}: {val}")
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def merge_facts(prior: dict[str, str], patch: dict[str, str]) -> dict[str, str]:
    out = {str(k).strip(): str(v).strip() for k, v in prior.items() if str(k).strip()}
    for key, value in patch.items():
        k = str(key).strip()
        if not k:
            continue
        v = str(value).strip() if value is not None else ""
        if not v:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def parse_facts_json(raw: str) -> dict[str, str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    # Strip optional markdown fence
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try first {...} blob
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for k, v in data.items():
        key = str(k).strip()
        if not key:
            continue
        if v is None:
            out[key] = ""
        elif isinstance(v, (str, int, float, bool)):
            out[key] = str(v).strip()
        else:
            out[key] = json.dumps(v, ensure_ascii=False)
    return out


def build_facts_extract_prompt(*, prior: dict[str, str], user_message: str) -> str:
    prior_json = json.dumps(prior or {}, ensure_ascii=False, indent=2)
    return (
        "Обнови словарь фактов диалога (ключ → значение) по новому сообщению пользователя.\n"
        "Сохраняй цель, ограничения, предпочтения, решения, договорённости.\n"
        "Верни ТОЛЬКО JSON-объект. Пустая строка как значение = удалить ключ. "
        "Неизвестные ключи из prior сохрани, если сообщение их не отменяет.\n\n"
        f"Текущие facts:\n{prior_json}\n\n"
        f"Сообщение пользователя:\n{user_message.strip()}\n"
    )
