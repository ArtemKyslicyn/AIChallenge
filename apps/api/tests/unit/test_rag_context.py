import asyncio

from app.domain.rag import NullRagClient, RagSearchResult, format_rag_system_context


def test_format_rag_empty() -> None:
    text = format_rag_system_context(RagSearchResult(query="q", hits=(), context=""))
    low = text.lower()
    assert "не найдено" in low or "фрагментов" in low
    assert "не знаешь" in low or "не знаю" in low
    assert "уточн" in low


def test_null_client_search() -> None:
    result = asyncio.run(NullRagClient().search("hi"))
    assert result.hits == ()
