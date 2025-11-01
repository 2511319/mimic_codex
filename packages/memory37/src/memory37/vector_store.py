"""Vector store interfaces and pgvector implementation for Memory37."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import sqrt
from typing import Callable, Iterable, Protocol, Sequence

from psycopg import Connection
from psycopg import sql


class EmbeddingProvider(Protocol):
    """Protocol for embedding provider (e.g., OpenAI)."""

    def embed(self, texts: Sequence[str], *, model: str | None) -> list[list[float]]:  # pragma: no cover - interface
        """Return embeddings for given texts."""


@dataclass
class VectorRecord:
    """Single vector record for storage."""

    item_id: str
    vector: list[float]
    metadata: dict[str, str]


class VectorStore(Protocol):
    """Abstract interface for vector storage."""

    def upsert(self, records: Iterable[VectorRecord]) -> None:  # pragma: no cover - interface
        """Insert or update vector records."""

    def query(self, vector: list[float], *, top_k: int, metadata_filter: dict[str, str] | None = None) -> list[VectorRecord]:  # pragma: no cover - interface
        """Return nearest neighbours."""


class MemoryVectorStore(VectorStore):
    """In-memory implementation used for tests and prototyping."""

    def __init__(self) -> None:
        self._records: list[VectorRecord] = []

    def upsert(self, records: Iterable[VectorRecord]) -> None:
        existing = {record.item_id: record for record in self._records}
        for record in records:
            existing[record.item_id] = record
        self._records = list(existing.values())

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[VectorRecord]:
        candidates = self._records
        if metadata_filter:
            candidates = [r for r in candidates if metadata_filter.items() <= r.metadata.items()]

        scored = []
        for record in candidates:
            score = _cosine_similarity(vector, record.vector)
            scored.append((score, record))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [record for _, record in scored[:top_k]]


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x * x for x in a))
    norm_b = sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class PgVectorStore(VectorStore):
    """PostgreSQL pgvector-backed store."""

    def __init__(
        self,
        connection_factory: Callable[[], Connection],
        *,
        table: str = "memory37_vectors",
        dimension: int = 1536,
    ) -> None:
        self._connection_factory = connection_factory
        self._table = table
        self._dimension = dimension
        self._schema_initialized = False

    def upsert(self, records: Iterable[VectorRecord]) -> None:
        records = list(records)
        if not records:
            return
        conn = self._connection_factory()
        try:
            self._ensure_schema(conn)
            insert_sql = sql.SQL(
                """
                INSERT INTO {table} (item_id, embedding, metadata)
                VALUES (%s, %s::vector, %s::jsonb)
                ON CONFLICT (item_id) DO UPDATE
                SET embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata
                """
            ).format(table=sql.Identifier(self._table))

            with conn.cursor() as cur:
                for record in records:
                    cur.execute(
                        insert_sql,
                        (
                            record.item_id,
                            _format_vector_literal(record.vector),
                            json.dumps(record.metadata),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()

    def query(
        self,
        vector: list[float],
        *,
        top_k: int,
        metadata_filter: dict[str, str] | None = None,
    ) -> list[VectorRecord]:
        conn = self._connection_factory()
        try:
            where_clause = sql.SQL("")
            params: list[object] = []
            if metadata_filter:
                where_clause = sql.SQL("WHERE metadata @> %s::jsonb")
                params.append(json.dumps(metadata_filter))

            query_sql = sql.SQL(
                """
                SELECT item_id, embedding, metadata
                FROM {table}
                {where}
                ORDER BY embedding <#> %s::vector
                LIMIT %s
                """
            ).format(table=sql.Identifier(self._table), where=where_clause)

            params.extend([_format_vector_literal(vector), top_k])

            with conn.cursor() as cur:
                cur.execute(query_sql, params)
                rows = cur.fetchall()

            results: list[VectorRecord] = []
            for item_id, embedding, metadata in rows:
                results.append(
                    VectorRecord(
                        item_id=item_id,
                        vector=_parse_vector(embedding),
                        metadata=dict(metadata) if isinstance(metadata, dict) else json.loads(metadata),
                    )
                )
            return results
        finally:
            conn.close()

    def _ensure_schema(self, conn: Connection) -> None:
        if self._schema_initialized:
            return
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            create_table_sql = sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {table} (
                    item_id TEXT PRIMARY KEY,
                    embedding vector({dimension}),
                    metadata JSONB NOT NULL DEFAULT '{{}}'
                )
                """
            ).format(
                table=sql.Identifier(self._table),
                dimension=sql.Literal(self._dimension),
            )
            cur.execute(create_table_sql)
        conn.commit()
        self._schema_initialized = True


def _format_vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(f"{x:.10f}" for x in vector) + "]"


def _parse_vector(value: object) -> list[float]:
    if isinstance(value, (list, tuple)):
        return [float(v) for v in value]
    if isinstance(value, str):
        stripped = value.strip()[1:-1] if value.startswith("[") and value.endswith("]") else value
        if not stripped:
            return []
        return [float(part) for part in stripped.split(",")]
    return []
