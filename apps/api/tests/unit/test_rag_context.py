import asyncio

from app.domain.rag import NullRagClient, RagSearchResult, format_rag_system_context


def test_format_rag_empty() -> None:
    text = format_rag_system_context(RagSearchResult(query="q", hits=(), context=""))
    assert "фрагментов" in text.lower() or "нет" in text.lower() or "не найдено" in text.lower()


def test_null_client_search() -> None:
    result = asyncio.run(NullRagClient().search("hi"))
    assert result.hits == ()
