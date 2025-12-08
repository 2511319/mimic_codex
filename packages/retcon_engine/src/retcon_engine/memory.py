from __future__ import annotations

from datetime import datetime
from typing import Any

from memory37.stores.base import GraphStore, VectorStore
from memory37.types import Chunk, GraphFact

from .models import CanonPatchCandidate, GlobalMetaSnapshot


class Memory37Sink:
    """Адаптер для записи снапшотов Retcon Engine в Memory37 и Graph домен."""

    def __init__(self, vector_store: VectorStore | None = None, graph_store: GraphStore | None = None) -> None:
        self._vector_store = vector_store
        self._graph_store = graph_store

    async def persist_snapshot(self, snapshot: GlobalMetaSnapshot) -> None:
        await self._store_meta(snapshot)
        await self._store_perception(snapshot)
        await self._store_canon_candidates(snapshot.candidates)

    async def _store_meta(self, snapshot: GlobalMetaSnapshot) -> None:
        if not self._vector_store:
            return
        meta_text = self._render_meta(snapshot)
        chunk = Chunk(
            id=f"world-meta:{snapshot.world_id}:{int(snapshot.collected_to.timestamp())}",
            domain="world_meta",
            text=meta_text,
            payload={},
            metadata={"world_id": snapshot.world_id, "collected_to": snapshot.collected_to.isoformat()},
        )
        await self._vector_store.upsert(domain="world_meta", items=[chunk])

    async def _store_perception(self, snapshot: GlobalMetaSnapshot) -> None:
        if not self._graph_store:
            return
        facts = []
        for edge in snapshot.influence.edges:
            facts.append(
                GraphFact(
                    node_id=edge.from_node,
                    type="world_perception",
                    properties={"world_id": snapshot.world_id},
                    relations=[
                        {
                            "to": edge.to_node,
                            "type": edge.relation_type,
                            "weight": edge.weight,
                            "sign": edge.sign,
                            "last_event_at": edge.last_event_at.isoformat() if edge.last_event_at else None,
                        }
                    ],
                )
            )
        if facts:
            await self._graph_store.upsert_facts(facts)

    async def _store_canon_candidates(self, candidates: list[CanonPatchCandidate]) -> None:
        if not self._vector_store:
            return
        items: list[Chunk] = []
        for candidate in candidates:
            text = f"Кандидат L0: {candidate.target}. Изменение: {candidate.change}. Основание: {candidate.reason}."
            items.append(
                Chunk(
                    id=f"canon-candidate:{candidate.candidate_id}",
                    domain="lore_canon",
                    text=text,
                    payload={"score": candidate.score},
                    metadata={"world_id": candidate.world_id},
                )
            )
        if items:
            await self._vector_store.upsert(domain="lore_canon", items=items)

    def _render_meta(self, snapshot: GlobalMetaSnapshot) -> str:
        def format_block(title: str, data: dict[str, Any]) -> str:
            if not data:
                return f"{title}: n/a"
            lines = [f"{title}:"]
            for key, value in data.items():
                lines.append(f"- {key}: {value}")
            return "\n".join(lines)

        return "\n\n".join(
            [
                f"World {snapshot.world_id} meta {snapshot.collected_from.isoformat()} -> {snapshot.collected_to.isoformat()}",
                format_block("NPC", snapshot.npc_stats),
                format_block("Factions", snapshot.faction_stats),
                format_block("Choices", snapshot.choice_stats),
                format_block("Players", snapshot.player_behavior),
            ]
        )


__all__ = ["Memory37Sink"]
