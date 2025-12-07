from __future__ import annotations

from ..types import EpisodicSummary
from ..stores.base import VectorStore


async def session_fetch(store: VectorStore, party_id: str, *, k: int = 8, version_id: str | None = None) -> list[EpisodicSummary]:
    results = await store.search(domain="episode", query=party_id, k_vector=k, filters={"party_id": party_id, "knowledge_version_id": version_id} if version_id else None)
    summaries: list[EpisodicSummary] = []
    for score in results:
        try:
            summaries.append(EpisodicSummary.model_validate(score.chunk.payload or {}))
        except Exception:
            continue
    return summaries
