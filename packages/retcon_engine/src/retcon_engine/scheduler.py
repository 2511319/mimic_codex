from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Iterable
from uuid import uuid4

from .memory import Memory37Sink
from .models import (
    CanonPatchCandidate,
    GlobalMetaSnapshot,
    InfluenceEdge,
    InfluenceGraph,
    RetconPackage,
)
from .repository import RetconRepository


class GlobalTickScheduler:
    """Планировщик глобальных тиков и агрегации RetconPackage."""

    def __init__(
        self,
        repository: RetconRepository,
        *,
        memory_sink: Memory37Sink | None = None,
        tick_period: timedelta = timedelta(days=3),
    ) -> None:
        self._repository = repository
        self._memory_sink = memory_sink
        self._tick_period = tick_period

    async def run_tick(self, *, now: datetime | None = None) -> GlobalMetaSnapshot:
        now = now or datetime.utcnow()
        since = self._repository.last_tick_at or now - self._tick_period
        packages = self._repository.list_packages_since(since)
        snapshot = self._aggregate(packages, since, now)
        self._repository.add_snapshot(snapshot)
        if self._memory_sink:
            await self._memory_sink.persist_snapshot(snapshot)
        return snapshot

    def _aggregate(self, packages: Iterable[RetconPackage], since: datetime, now: datetime) -> GlobalMetaSnapshot:
        npc_stats: Counter[str] = Counter()
        faction_stats: Counter[str] = Counter()
        choice_stats: Counter[str] = Counter()
        player_behavior: Counter[str] = Counter()
        edges: list[InfluenceEdge] = []
        for package in packages:
            edges.extend(self._edges_from_deltas(package))
            self._collect_entity_stats(package, npc_stats, faction_stats, player_behavior)
            for meta_key, value in package.meta_stats.items():
                choice_stats[meta_key] += int(value) if isinstance(value, int) else 1

        world_id = self._world_id(packages)
        candidates = self._build_candidates(world_id, npc_stats, faction_stats)
        influence_graph = InfluenceGraph(world_id=world_id, edges=edges)
        influence_graph.merge_edges(edges)

        return GlobalMetaSnapshot(
            world_id=world_id,
            collected_from=since,
            collected_to=now,
            influence=influence_graph,
            npc_stats=dict(npc_stats),
            faction_stats=dict(faction_stats),
            choice_stats=dict(choice_stats),
            player_behavior=dict(player_behavior),
            candidates=candidates,
        )

    def _collect_entity_stats(
        self,
        package: RetconPackage,
        npc_stats: Counter[str],
        faction_stats: Counter[str],
        player_behavior: Counter[str],
    ) -> None:
        for delta in package.world_deltas:
            entity_type = (delta.get("entityType") or delta.get("type") or "").lower()
            change = (delta.get("change") or delta.get("status") or "").lower()
            target_id = delta.get("entityId") or delta.get("npcId") or delta.get("factionId") or "unknown"
            if entity_type == "npc":
                npc_stats[f"{target_id}:{change or 'delta'}"] += 1
            elif entity_type in {"faction", "city", "location"}:
                faction_stats[f"{target_id}:{change or 'delta'}"] += 1
            if mood := delta.get("playerBehavior"):
                player_behavior[str(mood).lower()] += 1

    def _edges_from_deltas(self, package: RetconPackage) -> list[InfluenceEdge]:
        edges: list[InfluenceEdge] = []
        for delta in package.world_deltas:
            source = delta.get("sourceId") or package.campaign_run_id
            target = delta.get("entityId") or delta.get("npcId") or delta.get("factionId")
            if not target:
                continue
            relation = delta.get("relation") or delta.get("change") or "influenced"
            weight = float(delta.get("weight", 1))
            sign = "POSITIVE" if weight >= 0 else "NEGATIVE"
            edges.append(
                InfluenceEdge(
                    from_node=str(source),
                    to_node=str(target),
                    relation_type=str(relation),
                    weight=abs(weight),
                    sign=sign,
                    last_event_at=package.received_at,
                )
            )
        return edges

    def _build_candidates(
        self, world_id: str, npc_stats: Counter[str], faction_stats: Counter[str]
    ) -> list[CanonPatchCandidate]:
        candidates: list[CanonPatchCandidate] = []
        for key, count in list(npc_stats.items()) + list(faction_stats.items()):
            if count < 2:
                continue
            target, change = key.split(":", maxsplit=1)
            reason = f"Повторяющийся исход '{change}' наблюдён {count} раз"
            candidates.append(
                CanonPatchCandidate(
                    candidate_id=str(uuid4()),
                    world_id=world_id,
                    target=target,
                    change=change,
                    reason=reason,
                    score=float(count),
                )
            )
        return candidates

    def _world_id(self, packages: Iterable[RetconPackage]) -> str:
        for package in packages:
            return package.world_id
        return "default"


__all__ = ["GlobalTickScheduler"]
