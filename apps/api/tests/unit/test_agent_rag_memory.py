"""Day 25 — workshop run injects RAG context and returns sources."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.application.agent_run import run_agent_with_dialog
from app.domain.agent_definition import AgentDefinition
from app.domain.agent_dialog import AgentDialog
from app.domain.entities import AUTO_MODEL, CompletionResult
from app.domain.rag import NullRagClient, RagChunkHit, RagSearchResult


class _MemDialogs:
    def __init__(self) -> None:
        self.saved: AgentDialog | None = None

    async def get(self, dialog_id):  # noqa: ANN001
        return self.saved if self.saved and self.saved.id == dialog_id else None

    async def get_by_client_draft(self, *, client_visitor_id: str, client_draft_id: str):
        if (
            self.saved
            and self.saved.client_visitor_id == client_visitor_id
            and self.saved.client_draft_id == client_draft_id
        ):
            return self.saved
        return None

    async def save(self, dialog: AgentDialog) -> AgentDialog:
        self.saved = dialog
        return dialog


class _FakeRouter:
    last_system: str = ""

    async def complete_chat(
        self,
        messages,
        preferred_model: str = "auto",
        *,
        generation=None,
        tools=None,
    ):  # noqa: ANN001
        self.last_system = messages[0].content if messages else ""
        return CompletionResult(content="Ответ по базе про :443.", model_id="fake-model")


class _StubRag:
    async def search(self, query: str, *, top_k: int = 6, mode: str | None = None) -> RagSearchResult:
        hit = RagChunkHit(
            chunk_id="c1",
            text="Публичный :443 → xray Reality → nginx :8443 → web :18080.",
            source="deploy.md",
            title="Deploy",
            section="Edge",
            strategy="structural",
            score=0.81,
        )
        return RagSearchResult(
            query=query,
            hits=(hit,),
            context=hit.text,
            embed_model="stub-embed",
            query_rewritten=query,
            retrieval={"mode": mode or "full", "hits_pre": 1, "hits_post": 1},
        )

    async def add_document_text(self, **kwargs):  # noqa: ANN003
        return {}

    async def add_document_bytes(self, **kwargs):  # noqa: ANN003
        return {}

    async def stats(self):
        return {}

    async def patch_settings(self, payload):  # noqa: ANN001
        return {}

    async def reindex(self, strategy=None):  # noqa: ANN001
        return {}

    async def heal(self):
        return {}


@pytest.mark.asyncio
async def test_run_agent_with_dialog_returns_rag_sources() -> None:
    dialogs = _MemDialogs()
    definition = AgentDefinition(
        name="rag-mem",
        system_prompt="Ты ассистент.",
        preferred_model=AUTO_MODEL,
        temperature=0.2,
        max_tokens=200,
    )
    router = _FakeRouter()
    outcome, saved = await run_agent_with_dialog(
        definition=definition,
        message="Куда ходит :443?",
        router=router,  # type: ignore[arg-type]
        dialogs=dialogs,  # type: ignore[arg-type]
        client_visitor_id="visitor-1",
        client_draft_id="rag-memory-day25",
        enabled=True,
        max_message_chars=4000,
        use_rag=True,
        rag_client=_StubRag(),  # type: ignore[arg-type]
        rag_mode="full",
    )
    assert outcome.result.model_id == "fake-model"
    assert len(outcome.rag_sources) == 1
    assert outcome.rag_sources[0]["chunk_id"] == "c1"
    assert outcome.rag_embed_model == "stub-embed"
    assert "xray" in router.last_system.lower() or ":443" in router.last_system
    assert len(saved.messages) == 2


@pytest.mark.asyncio
async def test_null_rag_still_returns_empty_sources_list() -> None:
    dialogs = _MemDialogs()
    definition = AgentDefinition(
        name="rag-mem",
        system_prompt="Ты ассистент.",
        preferred_model=AUTO_MODEL,
        temperature=None,
        max_tokens=None,
    )
    # Seed dialog so history path is warm.
    dialogs.saved = AgentDialog(
        id=uuid4(),
        client_visitor_id="visitor-1",
        visitor_hash=None,
        client_draft_id="rag-memory-day25",
        name="rag-mem",
        system_prompt="Ты ассистент.",
        preferred_model=AUTO_MODEL,
        temperature=None,
        max_tokens=None,
        messages=[],
        summary_text="",
        summary_until_count=0,
        facts={},
        working_memory={"goal": "разобрать стенд"},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    outcome, _saved = await run_agent_with_dialog(
        definition=definition,
        message="Что такое Guest MCP?",
        router=_FakeRouter(),  # type: ignore[arg-type]
        dialogs=dialogs,  # type: ignore[arg-type]
        client_visitor_id="visitor-1",
        client_draft_id="rag-memory-day25",
        enabled=True,
        max_message_chars=4000,
        use_rag=True,
        rag_client=NullRagClient(),
        rag_mode="full",
    )
    assert outcome.rag_sources == ()
    assert outcome.result.content
