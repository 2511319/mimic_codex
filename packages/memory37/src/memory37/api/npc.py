from __future__ import annotations

from ..types import NPCProfile
from ..stores.base import VectorStore


async def npc_profile(store: VectorStore, npc_id: str, party_id: str | None = None, version_id: str | None = None) -> NPCProfile | None:
    filters = {"npc_id": npc_id}
    if version_id:
        filters["knowledge_version_id"] = version_id
    results = await store.search(domain="npc", query=npc_id, k_vector=1, filters=filters)
    if not results:
        return None
    try:
        return NPCProfile.model_validate(results[0].chunk.payload or {})
    except Exception:
        return None
