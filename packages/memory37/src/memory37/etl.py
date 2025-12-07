"""ETL helpers for loading knowledge items into vector store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .domain import KnowledgeItem
from .vector_store import EmbeddingProvider, VectorRecord, VectorStore


@dataclass
class ETLPipeline:
    """Helper for batching knowledge items and storing embeddings."""

    vector_store: VectorStore
    embedding_provider: EmbeddingProvider
    embedding_model: str | None = None

    def ingest(self, items: Sequence[KnowledgeItem]) -> None:
        texts = [item.content for item in items]
        embeddings = self.embedding_provider.embed(texts, model=self.embedding_model)
        records: list[VectorRecord] = []
        for item, vector in zip(items, embeddings, strict=True):
            metadata = {
                "domain": item.domain,
                **item.metadata,
                "content": item.content,
            }
            if item.knowledge_version_id:
                metadata["knowledge_version_id"] = item.knowledge_version_id
            if item.expires_at:
                metadata["expires_at"] = item.expires_at.isoformat()
            records.append(VectorRecord(item_id=item.item_id, vector=vector, metadata=metadata))
        self.vector_store.upsert(records)
