"""Hybrid retrieval combining dense vectors and lexical scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import sqrt
from typing import Dict, Iterable, List, Protocol, Sequence

from .domain import KnowledgeItem
from .vector_store import EmbeddingProvider, VectorRecord, VectorStore


def _tokenize(text: str) -> list[str]:
    return [token for token in text.lower().split() if token]


def _lexical_score(text: str, query_terms: Sequence[str]) -> float:
    tokens = _tokenize(text)
    score = 0.0
    for term in query_terms:
        for token in tokens:
            if token == term or token.startswith(term):
                score += 1.0
    return score


@dataclass
class HybridRetriever:
    """Hybrid retriever using vector similarity + lexical scoring."""

    vector_store: VectorStore
    embedding_provider: EmbeddingProvider
    embedding_model: str
    alpha: float = 0.6
    documents: Dict[str, KnowledgeItem] = field(default_factory=dict)
    rerank_provider: "RerankProvider" | None = None

    def index(self, items: Iterable[KnowledgeItem]) -> None:
        items = list(items)
        if not items:
            return
        self.documents.update({item.item_id: item for item in items})
        embeddings = self.embedding_provider.embed([item.content for item in items], model=self.embedding_model)
        records: List[VectorRecord] = []
        for item, vector in zip(items, embeddings, strict=True):
            records.append(VectorRecord(item_id=item.item_id, vector=vector, metadata={"domain": item.domain, **item.metadata}))
        self.vector_store.upsert(records)

    def query(self, text: str, *, top_k: int = 5) -> list[tuple[KnowledgeItem, float]]:
        query_embedding = self.embedding_provider.embed([text], model=self.embedding_model)[0]
        vector_candidates = self.vector_store.query(query_embedding, top_k=top_k * 3)
        query_terms = _tokenize(text)

        results: list[tuple[KnowledgeItem, float]] = []
        for record in vector_candidates:
            item = self.documents.get(record.item_id)
            if not item:
                item = _record_to_item(record)
                if not item:
                    continue

            dense_score = _cosine(query_embedding, record.vector)
            lexical = _lexical_score(item.content, query_terms)
            combined = self.alpha * dense_score + (1 - self.alpha) * lexical
            results.append((item, combined))

        results.sort(key=lambda entry: entry[1], reverse=True)
        results = results[: top_k * 2]

        if self.rerank_provider:
            reranked = self.rerank_provider.rerank(text, [item for item, _ in results])
            return reranked[:top_k]

        return results[:top_k]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class RerankProvider(Protocol):
    """Protocol for LLM-based reranker."""

    def rerank(self, query: str, items: Sequence[KnowledgeItem]) -> list[tuple[KnowledgeItem, float]]:  # pragma: no cover - interface
        """Return items sorted by relevance with scores."""


def _record_to_item(record: VectorRecord) -> KnowledgeItem | None:
    metadata = record.metadata or {}
    content = metadata.get("content")
    if content is None:
        return None
    meta_copy = dict(metadata)
    meta_copy.pop("content", None)
    domain = meta_copy.get("domain", "scene")
    return KnowledgeItem(item_id=record.item_id, domain=domain, content=content, metadata=meta_copy)
