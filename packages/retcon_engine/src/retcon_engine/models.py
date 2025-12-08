from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Iterable

from pydantic import BaseModel, Field


class Importance(str, Enum):
    MICRO = "MICRO"
    MESO = "MESO"
    MACRO = "MACRO"


class WorldEventType(str, Enum):
    KILL_NPC = "KILL_NPC"
    SPARE_NPC = "SPARE_NPC"
    HELP_FACTION = "HELP_FACTION"
    DESTROY_LOCATION = "DESTROY_LOCATION"
    SAVE_CITY = "SAVE_CITY"
    GENERIC = "GENERIC"


class CanonPatchDecision(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"


class RetconPackage(BaseModel):
    world_id: str = Field(..., alias="worldId")
    campaign_template_id: str = Field(..., alias="campaignTemplateId")
    campaign_run_id: str = Field(..., alias="campaignRunId")
    season_version: str = Field(..., alias="seasonVersion")
    world_deltas: list[dict[str, Any]] = Field(default_factory=list, alias="worldDeltas")
    player_impact: list[dict[str, Any]] = Field(default_factory=list, alias="playerImpact")
    meta_stats: dict[str, Any] = Field(default_factory=dict, alias="metaStats")
    received_at: datetime = Field(default_factory=datetime.utcnow)


class WorldEvent(BaseModel):
    id: str
    world_id: str
    campaign_run_id: str
    campaign_template_id: str
    actors: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    type: WorldEventType = WorldEventType.GENERIC
    importance: Importance = Importance.MICRO
    tags: list[str] = Field(default_factory=list)
    result: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class InfluenceEdge(BaseModel):
    from_node: str
    to_node: str
    relation_type: str
    weight: float = 0.0
    sign: str = "NEUTRAL"
    last_event_at: datetime | None = None
    decay: float | None = None


class InfluenceGraph(BaseModel):
    world_id: str
    edges: list[InfluenceEdge] = Field(default_factory=list)

    def merge_edges(self, new_edges: Iterable[InfluenceEdge]) -> None:
        merged: dict[tuple[str, str, str], InfluenceEdge] = {
            (edge.from_node, edge.to_node, edge.relation_type): edge for edge in self.edges
        }
        for edge in new_edges:
            key = (edge.from_node, edge.to_node, edge.relation_type)
            existing = merged.get(key)
            if existing:
                existing.weight += edge.weight
                existing.last_event_at = max(filter(None, [existing.last_event_at, edge.last_event_at]))
                existing.sign = edge.sign or existing.sign
            else:
                merged[key] = edge
        self.edges = list(merged.values())


class CanonPatchCandidate(BaseModel):
    candidate_id: str
    world_id: str
    target: str
    change: str
    reason: str
    score: float = 0.0


class CanonPatchRequest(BaseModel):
    candidate_id: str
    decision: CanonPatchDecision
    applied_by: str


class CanonPatchRecord(BaseModel):
    candidate_id: str
    decision: CanonPatchDecision
    applied_by: str
    applied_at: datetime
    new_world_version: str


class GlobalMetaSnapshot(BaseModel):
    world_id: str
    collected_from: datetime
    collected_to: datetime
    influence: InfluenceGraph
    npc_stats: dict[str, Any] = Field(default_factory=dict)
    faction_stats: dict[str, Any] = Field(default_factory=dict)
    choice_stats: dict[str, Any] = Field(default_factory=dict)
    player_behavior: dict[str, Any] = Field(default_factory=dict)
    candidates: list[CanonPatchCandidate] = Field(default_factory=list)


__all__ = [
    "Importance",
    "WorldEventType",
    "CanonPatchDecision",
    "RetconPackage",
    "WorldEvent",
    "InfluenceEdge",
    "InfluenceGraph",
    "CanonPatchCandidate",
    "CanonPatchRequest",
    "CanonPatchRecord",
    "GlobalMetaSnapshot",
]
