from app.application.public_safety import (
    filter_rag_for_public,
    is_sensitive_rag_source,
    public_safety_system,
)
from app.domain.rag import RagChunkHit, RagSearchResult, format_rag_system_context


def test_sensitive_sources() -> None:
    assert is_sensitive_rag_source("docs/env-local.md")
    assert is_sensitive_rag_source("scripts/deploy.sh")
    assert is_sensitive_rag_source("AGENTS.md")
    assert not is_sensitive_rag_source("docs/project-structure.md")
    assert not is_sensitive_rag_source("docs/support-faq.md")


def test_filter_drops_edge_docs() -> None:
    hits = (
        RagChunkHit(
            chunk_id="1",
            text="internal host note",
            source="docs/env-local.md",
            title="edge",
            section="",
            strategy="raw",
            score=0.9,
        ),
        RagChunkHit(
            chunk_id="2",
            text="modular monolith",
            source="docs/project-structure.md",
            title="struct",
            section="",
            strategy="raw",
            score=0.8,
        ),
    )
    raw = RagSearchResult(query="443", hits=hits, context="")
    filtered = filter_rag_for_public(raw)
    assert len(filtered.hits) == 1
    assert filtered.hits[0].source == "docs/project-structure.md"
    assert filtered.retrieval and filtered.retrieval.get("public_safety_filtered") is True


def test_public_vs_admin_prompt() -> None:
    public = public_safety_system(is_admin=False)
    admin = public_safety_system(is_admin=True)
    assert "публичного" in public.lower() or "запрет" in public.lower()
    assert "сервера" in public.lower()
    assert "админ" in admin.lower()


def test_rag_context_public_forbids_port_chain() -> None:
    hit = RagChunkHit(
        chunk_id="1",
        text="hello",
        source="docs/project-structure.md",
        title="t",
        section="",
        strategy="raw",
        score=1.0,
    )
    text = format_rag_system_context(
        RagSearchResult(query="q", hits=(hit,), context=""),
        allow_ops_detail=False,
    )
    assert "не пересказывай" in text.lower() or "публичный" in text.lower()
    assert "собери цепочку" not in text.lower()


def test_rag_context_admin_allows_port_chain() -> None:
    hit = RagChunkHit(
        chunk_id="1",
        text="hello",
        source="docs/env-local.md",
        title="t",
        section="",
        strategy="raw",
        score=1.0,
    )
    text = format_rag_system_context(
        RagSearchResult(query="q", hits=(hit,), context=""),
        allow_ops_detail=True,
    )
    assert "операционные" in text.lower()
