from __future__ import annotations

from ..types import ArtCard
from ..stores.base import VectorStore


async def art_suggest(store: VectorStore, scene_id: str, *, version_id: str | None = None) -> ArtCard | None:
    filters = {"scene_id": scene_id}
    if version_id:
        filters["knowledge_version_id"] = version_id
    results = await store.search(domain="art", query=scene_id, k_vector=1, filters=filters)
    if not results:
        return None
    try:
        return ArtCard.model_validate({"sceneId": scene_id, **results[0].chunk.metadata, **results[0].chunk.payload})
    except Exception:
        return None
