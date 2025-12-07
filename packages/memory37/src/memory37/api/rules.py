from __future__ import annotations

from ..types import Chunk
from ..stores.base import VectorStore


async def rules_lookup(store: VectorStore, *, term: str | None = None, rule_id: str | None = None, k: int = 8, version_id: str | None = None) -> list[Chunk]:
    query = term or rule_id or ""
    filters = {"knowledge_version_id": version_id} if version_id else None
    results = await store.search(domain="srd", query=query, k_vector=k, filters=filters)
    return [score.chunk for score in results]
