"""RAG service settings — env names only; never commit secret values."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", protected_namespaces=())

    rag_host: str = "0.0.0.0"
    rag_port: int = 18766
    rag_shared_token: str = ""
    rag_data_dir: str = "/app/data"
    rag_corpus_dir: str = "/app/corpus"
    rag_chunk_strategy: str = "structural"  # fixed | structural
    rag_fixed_size: int = 800
    rag_fixed_overlap: int = 120
    rag_top_k: int = 6
    #: Retrieve this many candidates before filter/rerank.
    rag_top_k_pre: int = 20
    #: Keep at most this many after filter/rerank.
    rag_top_k_post: int = 6
    #: Drop hits with cosine score below this (filtered/full modes).
    rag_min_score: float = 0.18
    #: Default retrieval mode: raw | filtered | full
    rag_mode: str = "full"

    #: Empty = embedded Qdrant under RAG_DATA_DIR/qdrant; else http(s) URL.
    qdrant_url: str = ""
    qdrant_collection: str = "aichallenge_rag"

    embedding_provider: str = "api"  # api | local | fake
    embedding_model: str = "text-embedding-3-small"
    embedding_dims: int = 64  # used by fake; API uses provider dims
    llm_base_url: str = "https://routerai.ru/api/v1"
    llm_api_key: str = ""
    routerai_key: str = ""
    local_embeddings_enabled: bool = False
    local_embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    def data_path(self) -> Path:
        return Path(self.rag_data_dir)

    def corpus_path(self) -> Path:
        return Path(self.rag_corpus_dir)

    def effective_api_key(self) -> str:
        return (self.llm_api_key or self.routerai_key or "").strip()

    def effective_provider(self) -> str:
        if self.local_embeddings_enabled and self.embedding_provider == "local":
            return "local"
        if self.embedding_provider == "local" and not self.local_embeddings_enabled:
            return "api" if self.effective_api_key() else "fake"
        if self.embedding_provider == "api" and not self.effective_api_key():
            return "fake"
        return self.embedding_provider


@lru_cache
def get_settings() -> Settings:
    return Settings()
