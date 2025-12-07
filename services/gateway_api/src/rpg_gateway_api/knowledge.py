"""Knowledge search integration using Memory37."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

try:  # pragma: no cover - optional dependency
    import psycopg  # type: ignore
except Exception:  # pragma: no cover - degrade gracefully if not installed
    psycopg = None  # type: ignore[assignment]

from pydantic import BaseModel, Field

from memory37 import KnowledgeVersion, KnowledgeVersionRegistry
from memory37.embedding import OpenAIEmbeddingProvider, TokenFrequencyEmbeddingProvider
from memory37.stores.pgvector_store import InMemoryVectorStore, PgVectorWrapper
from memory37.ingest import load_knowledge_items_from_yaml
from memory37.types import Chunk, ChunkScore

from .config import Settings

logger = logging.getLogger(__name__)


class KnowledgeSearchResult(BaseModel):
    item_id: str
    score: float
    content_snippet: str = Field(..., description="First 160 chars of content")
    metadata: dict[str, str]


class KnowledgeService:
    """Обёртка над Memory37 core для gateway."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._available = False
        self._version_registry = KnowledgeVersionRegistry()
        self._version_id: str | None = None
        self._store: PgVectorWrapper | InMemoryVectorStore | None = None
        self._domains = ["scene", "npc", "lore", "srd", "art"]
        self._alpha = 0.7
        self._load()

    @property
    def available(self) -> bool:
        return self._available

    async def search(self, query: str, *, top_k: int = 5) -> list[KnowledgeSearchResult]:
        if not self._available or not self._store:
            raise RuntimeError("Knowledge search is not configured")
        version_filter = {"knowledge_version_id": self._version_id} if self._version_id else {}
        merged: list[ChunkScore] = []
        for domain in self._domains:
            try:
                results = await self._store.search(domain=domain, query=query, k_vector=top_k, filters=version_filter)
                merged.extend(results)
            except Exception:
                continue
        merged.sort(key=lambda r: r.score, reverse=True)
        merged = merged[:top_k]
        return [
            KnowledgeSearchResult(
                item_id=item.chunk.id,
                score=item.score,
                content_snippet=item.chunk.text[:160].replace("\n", " "),
                metadata={k: str(v) for k, v in item.chunk.metadata.items()},
            )
            for item in merged
        ]

    def _load(self) -> None:
        env_path_present = "KNOWLEDGE_SOURCE_PATH" in os.environ
        env_db_present = "KNOWLEDGE_DATABASE_URL" in os.environ and os.environ.get("KNOWLEDGE_DATABASE_URL")
        if not env_path_present and not env_db_present:
            logger.info("KNOWLEDGE_SOURCE_PATH не задан в окружении, knowledge search отключён")
            self._available = False
            return

        version_id = getattr(self._settings, "knowledge_version_id", None) or "kv_default"
        version_alias = getattr(self._settings, "knowledge_version_alias", None) or "lore_latest"
        self._version_registry.register(
            KnowledgeVersion(
                id=version_id,
                semver=self._settings.api_version,
                kind="lore",
                status="latest",
            )
        )
        self._version_registry.set_alias(version_alias, version_id)
        self._version_id = self._version_registry.get_version_id(alias=version_alias)

        provider = self._create_embedding_provider()
        # Если задан source-path (локальный ingest) и не используется OpenAI, предпочитаем in-memory, чтобы избежать несовпадения размерности эмбеддингов с pgvector.
        using_local_ingest = bool(self._settings.knowledge_source_path)
        prefer_memory = using_local_ingest and not self._settings.knowledge_use_openai

        if self._settings.knowledge_database_url and psycopg is not None and not prefer_memory:
            self._store = PgVectorWrapper(
                lambda: psycopg.connect(self._settings.knowledge_database_url),
                table=self._settings.knowledge_vector_table,
                dimension=self._settings.knowledge_vector_dimension,
                embedding_provider=provider,
                embedding_model=self._settings.knowledge_openai_embedding_model,
                alpha=self._alpha,
            )
        else:
            if self._settings.knowledge_database_url and psycopg is None:
                logger.warning("KNOWLEDGE_DATABASE_URL задан, но psycopg не установлен; используем in-memory store.")
            if prefer_memory and self._settings.knowledge_database_url:
                logger.info("KNOWLEDGE_SOURCE_PATH задан, используем in-memory store для локального ingest.")
            self._store = InMemoryVectorStore(
                embedding_provider=provider,
                embedding_model=self._settings.knowledge_openai_embedding_model,
                alpha=self._alpha,
            )

        items = self._load_items()
        if not items and isinstance(self._store, InMemoryVectorStore):
            logger.info("Knowledge source not provided; knowledge search disabled")
            self._available = False
            return

        if items:
            asyncio.run(self._ingest_items(items))

        # Очистка TTL если поддерживается
        cleanup = getattr(self._store, "cleanup_expired", None)
        if callable(cleanup):
            try:
                cleanup()
            except Exception:  # pragma: no cover
                pass

        self._available = True

    def _load_items(self) -> list:
        path_value = self._settings.knowledge_source_path
        if not path_value:
            return []
        source_path = Path(path_value)
        if not source_path.is_absolute():
            source_path = Path.cwd() / source_path
        if not source_path.exists():
            logger.warning("Knowledge source path %s not found", source_path)
            return []
        return load_knowledge_items_from_yaml(source_path, knowledge_version_id=self._version_id)

    async def _ingest_items(self, items: Iterable) -> None:
        if not self._store:
            return
        chunk_batches: dict[str, list[Chunk]] = {domain: [] for domain in self._domains}
        for item in items:
            meta = dict(item.metadata)
            if item.knowledge_version_id:
                meta["knowledge_version_id"] = item.knowledge_version_id
            if item.expires_at:
                meta["expires_at"] = item.expires_at.isoformat()
            chunk = Chunk(id=item.item_id, domain=item.domain, text=item.content, payload={}, metadata=meta)
            chunk_batches.setdefault(item.domain, []).append(chunk)
        for domain, chunks in chunk_batches.items():
            if not chunks:
                continue
            await self._store.upsert(domain=domain, items=chunks)

    def _create_embedding_provider(self):
        if self._settings.knowledge_use_openai:
            try:
                return OpenAIEmbeddingProvider(model=self._settings.knowledge_openai_embedding_model)
            except Exception:  # pragma: no cover - fallback
                return TokenFrequencyEmbeddingProvider()
        return TokenFrequencyEmbeddingProvider()

