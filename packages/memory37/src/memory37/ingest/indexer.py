from __future__ import annotations

from typing import Iterable

from .normalizer import normalize_srd, normalize_lore, normalize_episode, normalize_art
from .chunker import chunk_lore
from .embedder import Embedder
from ..types import Chunk, EpisodicSummary, ArtCard
from ..stores.base import VectorStore, GraphStore
from ..types import GraphFact


async def ingest_srd(store: VectorStore, embedder: Embedder, raw: str | dict, *, version_id: str | None = None, ttl_days: int | None = None) -> None:
    chunks = normalize_srd(raw)
    await _index(store, embedder, "srd", chunks, version_id=version_id, ttl_days=ttl_days)


async def ingest_lore(store: VectorStore, embedder: Embedder, raw: str | dict, *, version_id: str | None = None, ttl_days: int | None = None) -> None:
    chunks = normalize_lore(raw)
    chunks = chunk_lore(chunks)
    await _index(store, embedder, "lore", chunks, version_id=version_id, ttl_days=ttl_days)


async def ingest_episode(store: VectorStore, embedder: Embedder, summary: EpisodicSummary, *, version_id: str | None = None, ttl_days: int | None = 180) -> None:
    chunk = normalize_episode(summary)
    await _index(store, embedder, "episode", [chunk], version_id=version_id, ttl_days=ttl_days)


async def ingest_art(store: VectorStore, embedder: Embedder, card: ArtCard, *, version_id: str | None = None, ttl_days: int | None = None) -> None:
    chunk = normalize_art(card)
    await _index(store, embedder, "art", [chunk], version_id=version_id, ttl_days=ttl_days)


async def _index(store: VectorStore, embedder: Embedder, domain: str, chunks: Iterable[Chunk], *, version_id: str | None = None, ttl_days: int | None = None) -> None:
    texts = [c.text for c in chunks]
    embeddings = embedder.embed_texts(texts)
    enriched: list[Chunk] = []
    for chunk, vector in zip(chunks, embeddings, strict=True):
        metadata = {**chunk.metadata, "domain": domain}
        if version_id:
            metadata["knowledge_version_id"] = version_id
        expires_at = _expires_in_days(ttl_days)
        if expires_at:
            metadata["expires_at"] = expires_at
        enriched.append(
            Chunk(
                id=chunk.id,
                domain=chunk.domain,
                text=chunk.text,
                metadata=metadata,
                payload={**chunk.payload, "embedding": vector},
            )
        )
    await store.upsert(domain=domain, items=enriched)


def _expires_in_days(days: int | None) -> str | None:
    if not days or days <= 0:
        return None
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
