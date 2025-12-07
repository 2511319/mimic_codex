from __future__ import annotations

from typing import Iterable

from ..types import Chunk
from ..stores.base import VectorStore


async def lore_search(store: VectorStore, *, query: str, k: int = 8, version_id: str | None = None) -> list[Chunk]:
    filters = {"knowledge_version_id": version_id} if version_id else None
    results = await store.search(domain="lore", query=query, k_vector=k, filters=filters)
    return [score.chunk for score in results]
