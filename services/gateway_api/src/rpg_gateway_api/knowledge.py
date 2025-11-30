"""Knowledge search integration using Memory37."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

try:  # pragma: no cover - optional dependency
    import psycopg  # type: ignore
except Exception:  # pragma: no cover - degrade gracefully if not installed
    psycopg = None  # type: ignore[assignment]

from pydantic import BaseModel, Field

from memory37 import (
    ETLPipeline,
    HybridRetriever,
    MemoryVectorStore,
    OpenAIChatRerankProvider,
    OpenAIEmbeddingProvider,
    PgVectorStore,
    TokenFrequencyEmbeddingProvider,
)
from memory37.domain import KnowledgeItem
from memory37.ingest import load_knowledge_items_from_yaml

from .config import Settings

logger = logging.getLogger(__name__)


class KnowledgeSearchResult(BaseModel):
    item_id: str
    score: float
    content_snippet: str = Field(..., description="First 160 chars of content")
    metadata: dict[str, str]


class KnowledgeService:
    """Wraps Memory37 retriever for gateway endpoints."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._available = False
        self._retriever: HybridRetriever | None = None
        self._load()

    @property
    def available(self) -> bool:
        return self._available

    def search(self, query: str, *, top_k: int = 5) -> list[KnowledgeSearchResult]:
        if not self._available or not self._retriever:
            raise RuntimeError("Knowledge search is not configured")
        results = self._retriever.query(query, top_k=top_k)
        return [
            KnowledgeSearchResult(
                item_id=item.item_id,
                score=score,
                content_snippet=item.content[:160].replace("\n", " "),
                metadata=item.metadata,
            )
            for item, score in results
        ]

    def _load(self) -> None:
        provider = self._create_embedding_provider()
        documents: dict[str, KnowledgeItem] = {}
        items: list[KnowledgeItem] = []

        path_value = self._settings.knowledge_source_path
        if path_value:
            source_path = Path(path_value)
            if not source_path.is_absolute():
                source_path = Path.cwd() / source_path
            if source_path.exists():
                items = load_knowledge_items_from_yaml(source_path)
                documents = {item.item_id: item for item in items}

        store: MemoryVectorStore | PgVectorStore
        if self._settings.knowledge_database_url:
            if psycopg is None:
                logger.warning(
                    "KNOWLEDGE_DATABASE_URL задан, но пакет 'psycopg' не установлен. Используем in-memory store."
                )
                store = MemoryVectorStore()
            else:
                store = PgVectorStore(
                    lambda: psycopg.connect(self._settings.knowledge_database_url),
                    table=self._settings.knowledge_vector_table,
                    dimension=self._settings.knowledge_vector_dimension,
                )
                # Предполагаем, что данные уже загружены через memory37 CLI.
        else:
            store = MemoryVectorStore()
            if not items:
                return
            pipeline = ETLPipeline(
                vector_store=store,
                embedding_provider=provider,
                embedding_model=self._settings.knowledge_openai_embedding_model,
            )
            pipeline.ingest(items)

        rerank_provider = None
        if self._settings.knowledge_use_openai:
            try:
                rerank_provider = OpenAIChatRerankProvider(model=self._settings.knowledge_openai_rerank_model)
            except Exception:  # pragma: no cover - fail softly
                rerank_provider = None

        self._retriever = HybridRetriever(
            vector_store=store,
            embedding_provider=provider,
            embedding_model=self._settings.knowledge_openai_embedding_model,
            documents=documents,
            rerank_provider=rerank_provider,
        )
        self._available = True if documents or self._settings.knowledge_database_url else False

    def _create_embedding_provider(self):
        if self._settings.knowledge_use_openai:
            try:
                return OpenAIEmbeddingProvider(model=self._settings.knowledge_openai_embedding_model)
            except Exception:  # pragma: no cover - fallback to local provider
                return TokenFrequencyEmbeddingProvider()
        return TokenFrequencyEmbeddingProvider()

