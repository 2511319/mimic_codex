from __future__ import annotations

from typing import Callable, Iterable

from psycopg import Connection

from ..embedding import TokenFrequencyEmbeddingProvider
from ..vector_store import EmbeddingProvider, MemoryVectorStore, PgVectorStore as LegacyPgVectorStore, VectorRecord
from ..types import Chunk, ChunkScore
from .base import VectorStore


def _lexical_score(text: str, query: str) -> float:
    """Примитивный lexical/BM25-like скорер (по совпадению токенов)."""

    tokens = [t for t in text.lower().split() if t]
    q_tokens = [t for t in query.lower().split() if t]
    score = 0.0
    for qt in q_tokens:
        score += sum(1.0 for tok in tokens if tok.startswith(qt))
    return score


def _combine_scores(vector_score: float, lexical_score: float, *, alpha: float = 0.7) -> float:
    return alpha * vector_score + (1 - alpha) * lexical_score


class PgVectorWrapper(VectorStore):
    """Адаптер PgVectorStore с реальными embedding и гибридным скорингом."""

    def __init__(
        self,
        connection_factory: Callable[[], Connection],
        *,
        table: str = "memory37_vectors",
        dimension: int = 1536,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_model: str | None = None,
        alpha: float = 0.7,
    ) -> None:
        self._store = LegacyPgVectorStore(connection_factory, table=table, dimension=dimension)
        self._embedder = embedding_provider or TokenFrequencyEmbeddingProvider()
        self._embedding_model = embedding_model
        self._alpha = alpha

    async def upsert(self, *, domain: str, items: list[Chunk]) -> None:
        records = []
        texts: list[str] = []
        need_embed: list[int] = []
        for idx, item in enumerate(items):
            vector = item.payload.get("embedding")
            if not vector:
                need_embed.append(idx)
                texts.append(item.text)
        if need_embed:
            embeddings = self._embedder.embed(texts, model=self._embedding_model)
            for idx, emb in zip(need_embed, embeddings, strict=True):
                items[idx].payload["embedding"] = emb

        for item in items:
            vector = item.payload.get("embedding") or []
            metadata = {**item.metadata, "domain": domain, "content": item.text}
            records.append(VectorRecord(item_id=item.id, vector=vector, metadata=metadata))
        self._store.upsert(records)

    async def search(
        self,
        *,
        domain: str,
        query: str,
        k_vector: int,
        k_keyword: int | None = None,
        filters: dict | None = None,
    ) -> list[ChunkScore]:
        meta = {**(filters or {}), "domain": domain}
        query_vec = self._embedder.embed([query], model=self._embedding_model)[0]
        raw = self._store.query(query_vec, top_k=max(k_vector, k_keyword or k_vector), metadata_filter=meta)

        results: list[ChunkScore] = []
        for rec in raw:
            text = rec.metadata.get("content", "")
            vector_score = _cosine(query_vec, rec.vector)
            lexical = _lexical_score(text, query)
            combined = _combine_scores(vector_score, lexical, alpha=self._alpha)
            chunk = Chunk(id=rec.item_id, domain=domain, text=text, payload={}, metadata=rec.metadata)
            results.append(ChunkScore(chunk=chunk, score=combined))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k_vector]

    def cleanup_expired(self) -> None:
        """Вызывает очистку просроченных записей, если реализована."""

        try:
            self._store.cleanup_expired()
        except AttributeError:
            return


class InMemoryVectorStore(VectorStore):
    """In-memory реализация VectorStore с гибридным скорингом для тестов/CLI."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_model: str | None = None,
        alpha: float = 0.7,
    ) -> None:
        self._store = MemoryVectorStore()
        self._embedder = embedding_provider or TokenFrequencyEmbeddingProvider()
        self._embedding_model = embedding_model
        self._alpha = alpha

    async def upsert(self, *, domain: str, items: list[Chunk]) -> None:
        records: list[VectorRecord] = []
        vectors = self._embedder.embed([item.text for item in items], model=self._embedding_model)
        for item, vector in zip(items, vectors, strict=True):
            metadata = {**item.metadata, "domain": domain, "content": item.text}
            records.append(VectorRecord(item_id=item.id, vector=vector, metadata=metadata))
        self._store.upsert(records)

    async def search(
        self,
        *,
        domain: str,
        query: str,
        k_vector: int,
        k_keyword: int | None = None,
        filters: dict | None = None,
    ) -> list[ChunkScore]:
        query_vec = self._embedder.embed([query], model=self._embedding_model)[0]
        raw = self._store.query(query_vec, top_k=max(k_vector, k_keyword or k_vector), metadata_filter={**(filters or {}), "domain": domain})
        results: list[ChunkScore] = []
        for rec in raw:
            text = rec.metadata.get("content", "")
            vector_score = _cosine(query_vec, rec.vector)
            lexical = _lexical_score(text, query)
            combined = _combine_scores(vector_score, lexical, alpha=self._alpha)
            chunk = Chunk(id=rec.item_id, domain=domain, text=text, payload={}, metadata=rec.metadata)
            results.append(ChunkScore(chunk=chunk, score=combined))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:k_vector]

    def cleanup_expired(self) -> None:
        return


def _cosine(a: Iterable[float], b: Iterable[float]) -> float:
    a_list = list(a)
    b_list = list(b)
    if not a_list or not b_list or len(a_list) != len(b_list):
        return 0.0
    dot = sum(x * y for x, y in zip(a_list, b_list))
    norm_a = sum(x * x for x in a_list) ** 0.5
    norm_b = sum(y * y for y in b_list) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
