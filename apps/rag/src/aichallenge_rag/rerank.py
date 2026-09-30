"""Query rewrite + similarity filter + heuristic rerank."""

from __future__ import annotations

import re

from aichallenge_rag.store import SearchHit

# Filler / soft words stripped for rewrite (ru+en).
_FILLER = re.compile(
    r"\b("
    r"пожалуйста|скажи|расскажи|объясни|подскажи|можешь|нужно|"
    r"please|tell\s+me|explain|what\s+is|how\s+does|can\s+you|"
    r"а\s+что\s+такое|что\s+такое|как\s+работает"
    r")\b",
    re.IGNORECASE,
)
_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_.:/-]{2,}")

# Light synonym / alias expansion for this product corpus.
_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bguest\s*mcp\b", re.I), "Guest MCP Streamable HTTP"),
    (re.compile(r"\bсвой\s+сервер\b", re.I), "Guest MCP свой сервер"),
    (re.compile(r"\bmodel[_\s]?id\b", re.I), "model_id атрибуция модели"),
    (re.compile(r"\b:443\b|\bпорт\s*443\b", re.I), "443 Reality xray nginx 8443"),
    (re.compile(r"\breality\b", re.I), "VLESS Reality xray"),
    (re.compile(r"\bfakellm\b", re.I), "FakeLLM FakeLLMProvider"),
]


def rewrite_query(query: str) -> str:
    """Lightweight rewrite: strip filler, expand aliases, collapse spaces."""
    q = query.strip()
    if not q:
        return q
    rewritten = _FILLER.sub(" ", q)
    for pattern, expansion in _ALIASES:
        if pattern.search(rewritten):
            rewritten = f"{rewritten} {expansion}"
    rewritten = _SPACE.sub(" ", rewritten).strip()
    return rewritten or q


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def token_overlap(query: str, hit: SearchHit) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    blob = f"{hit.chunk.title} {hit.chunk.section} {hit.chunk.source} {hit.chunk.text[:800]}"
    d = _tokens(blob)
    if not d:
        return 0.0
    return len(q & d) / len(q)


def heuristic_rerank_score(query: str, hit: SearchHit, *, overlap_weight: float = 0.35) -> float:
    """Blend cosine similarity with lexical overlap against title/section/text."""
    overlap = token_overlap(query, hit)
    return (1.0 - overlap_weight) * float(hit.score) + overlap_weight * overlap


def apply_pipeline(
    query: str,
    hits: list[SearchHit],
    *,
    mode: str,
    min_score: float,
    top_k_post: int,
) -> tuple[list[SearchHit], dict[str, object]]:
    """
    Modes:
      raw      — keep order, truncate to top_k_post (no threshold)
      filtered — drop below min_score, then top_k_post
      full     — rewrite already applied upstream; filter + heuristic rerank + top_k_post
    """
    pre = len(hits)
    meta: dict[str, object] = {
        "mode": mode,
        "hits_pre": pre,
        "min_score": min_score,
        "top_k_post": top_k_post,
    }

    if mode == "raw":
        out = hits[:top_k_post]
        meta["hits_post"] = len(out)
        meta["dropped"] = max(0, pre - len(out))
        return out, meta

    filtered = [h for h in hits if float(h.score) >= min_score]
    meta["hits_after_threshold"] = len(filtered)

    if mode == "filtered":
        out = filtered[:top_k_post]
        meta["hits_post"] = len(out)
        meta["dropped"] = pre - len(out)
        return out, meta

    # full: rerank by blended score
    scored: list[tuple[float, SearchHit]] = []
    for h in filtered:
        blended = heuristic_rerank_score(query, h)
        scored.append((blended, SearchHit(chunk=h.chunk, score=blended)))
    scored.sort(key=lambda row: row[0], reverse=True)
    out = [h for _, h in scored[:top_k_post]]
    meta["hits_post"] = len(out)
    meta["dropped"] = pre - len(out)
    meta["rerank"] = "heuristic_overlap"
    return out, meta
