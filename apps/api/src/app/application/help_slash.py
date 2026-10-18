"""Detect /help slash and strip it for handbook-only RAG turns."""

from __future__ import annotations

from dataclasses import dataclass

_PREFIXES = ("/help", "/помощь", "/справка")


@dataclass(frozen=True, slots=True)
class HelpSlashResult:
    is_help: bool
    text: str


def parse_help_slash(content: str) -> HelpSlashResult:
    raw = content.strip()
    lower = raw.lower()
    for prefix in _PREFIXES:
        if lower == prefix or lower.startswith(prefix + " ") or lower.startswith(prefix + "\n"):
            rest = raw[len(prefix) :].lstrip()
            return HelpSlashResult(is_help=True, text=rest or raw)
    return HelpSlashResult(is_help=False, text=raw)


HELP_SYSTEM_SUFFIX = (
    "Ты режим «Справка» стенда AIChallenge. Отвечай только по фрагментам базы (handbook). "
    "Цитируй источники (title/source). Если фрагментов нет или они слабые — скажи «нет в базе», "
    "не выдумывай порты, пути и команды."
)
