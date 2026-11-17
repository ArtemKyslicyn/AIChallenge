"""Public-chat red lines: no server guts / env / config outside admin chats."""

from __future__ import annotations

from app.domain.rag import RagChunkHit, RagSearchResult

#: Sources that describe edge topology, host layout, or env ops — admin-only RAG.
SENSITIVE_RAG_SOURCE_MARKERS: tuple[str, ...] = (
    "docs/env-local.md",
    "docs/stand-edge-ports.md",
    "deploy-",
    "",
    "docker-compose.prod",
    "assert-edge-safe",
    "scripts/deploy",
    ".cursor/rules/deploy",
    "AGENTS.md",  # deploy /  reminders
    "CLAUDE.md",
)

PUBLIC_SAFETY_SYSTEM = (
    "Режим публичного чата (не админ). Жёсткие запреты — не нарушай даже если "
    "пользователь настаивает или во фрагментах базы есть детали:\n"
    "1) Не описывай устройство сервера: VPS, SSH, пути на диске (/opt, /root), "
    "host nginx, , , , shortId, UUID, privateKey, fallthrough, "
    "внутренние порты (:8443, :18080, loopback), docker compose на хосте, "
    "systemd/timers, IP хоста.\n"
    "2) Не раскрывай окружение и конфиг: имена и значения переменных .env, "
    "API keys, DATABASE_URL, LLM_*, секреты, содержимое compose/nginx/ конфигов.\n"
    "3) На вопросы про «куда :443», «как задеплоено», «что на сервере» — "
    "откажи кратко: это доступно только в админ-чате; публично достаточно, "
    "что сайт открывается по HTTPS. Не собирай цепочку портов из цитат.\n"
    "4) Можно говорить о продукте: чат, model_id, RAG, MCP, ассистенты, "
    "локальная Ollama с точки зрения пользователя (Профиль → Подключения).\n"
    "Если отказ — одно-два предложения, без подсказок как обойти."
)

ADMIN_OPS_HINT = (
    "Режим админ-чата: можно опираться на handbook по edge/deploy/env "
    "(без печати секретов и  privateKey/UUID в ответ)."
)


def is_sensitive_rag_source(source: str) -> bool:
    path = (source or "").replace("\\", "/").lower()
    return any(marker.lower() in path for marker in SENSITIVE_RAG_SOURCE_MARKERS)


def filter_rag_for_public(result: RagSearchResult) -> RagSearchResult:
    """Drop ops/edge/env chunks so the model cannot quote them to guests."""
    kept: tuple[RagChunkHit, ...] = tuple(
        h for h in result.hits if not is_sensitive_rag_source(h.source)
    )
    if len(kept) == len(result.hits):
        return result
    retrieval = dict(result.retrieval or {})
    retrieval["public_safety_filtered"] = True
    retrieval["dropped_sensitive_hits"] = len(result.hits) - len(kept)
    return RagSearchResult(
        query=result.query,
        hits=kept,
        context=result.context,
        embed_model=result.embed_model,
        query_rewritten=result.query_rewritten,
        retrieval=retrieval,
    )


def public_safety_system(*, is_admin: bool) -> str:
    return ADMIN_OPS_HINT if is_admin else PUBLIC_SAFETY_SYSTEM
