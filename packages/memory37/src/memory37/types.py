"""
Доменные модели Memory37 согласно спецификации (каркас).

Минимальные Pydantic-модели, пригодные для дальнейшей реализации API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class EpisodicSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary_id: str = Field(..., alias="summaryId")
    campaign_id: str = Field(..., alias="campaignId")
    party_id: str = Field(..., alias="partyId")
    scene_id: str | None = Field(None, alias="sceneId")
    when: datetime | None = None
    who: dict[str, Any] | None = None
    where: str | None = None
    what: list[str] | None = None
    flags: list[str] | None = None
    relations_delta: list[dict[str, Any]] | None = None
    notes: str | None = None
    version: str = "1.0.0"


class NPCProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    npc_id: str = Field(..., alias="npcId")
    name: str
    archetype: str
    voice_tts: str | None = Field(None, alias="voiceTts")
    static: dict[str, Any] | None = None
    dynamic: dict[str, Any] | None = None
    disposition: dict[str, int] = Field(default_factory=dict)
    memory: list[dict[str, Any]] = Field(default_factory=list)
    lore_refs: list[str] = Field(default_factory=list)
    version: str = "1.0.0"


class ArtCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    image_id: str = Field(..., alias="imageId")
    scene_id: str = Field(..., alias="sceneId")
    cdn_url: HttpUrl = Field(..., alias="cdnUrl")
    prompt_text: str = Field(..., alias="promptText")
    entities: dict[str, list[str]] = Field(default_factory=dict)
    visual_tags: list[str] = Field(default_factory=list, alias="visualTags")
    style: str | None = None
    seed: int | None = None
    model: str | None = None
    postproc: str | None = None
    moderation: dict[str, Any] | None = None


class Chunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    domain: Literal[
        "srd",
        "lore",
        "episode",
        "art",
        "scene",
        "npc",
        "quest",
        "event",
        "item",
        "lore_canon",
        "world_perception",
        "world_meta",
    ]
    text: str
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkScore(BaseModel):
    chunk: Chunk
    score: float


class GraphFact(BaseModel):
    node_id: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)
    relations: list[dict[str, Any]] = Field(default_factory=list)
