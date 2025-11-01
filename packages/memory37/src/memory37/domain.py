"""Domain models for Memory37 knowledge graph and scene storage."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl


class RelationDelta(BaseModel):
    """Represents an incremental change between two entities."""

    source_id: Annotated[str, Field(min_length=1)]
    target_id: Annotated[str, Field(min_length=1)]
    delta: Annotated[int, Field(ge=-5, le=5)]
    reason: Annotated[str, Field(min_length=1)]


class SceneChronicleEntry(BaseModel):
    """Single event inside a scene chronicle."""

    timestamp: datetime
    summary: Annotated[str, Field(min_length=1)]
    speaker: str | None = None


class SceneState(BaseModel):
    """Aggregated state of a scene."""

    scene_id: Annotated[str, Field(min_length=1)]
    campaign_id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    summary: Annotated[str, Field(min_length=1)]
    chronology: list[SceneChronicleEntry] = Field(default_factory=list)
    relations_delta: list[RelationDelta] = Field(default_factory=list)
    version: Annotated[str, Field(min_length=1)] = "1.0.0"
    tags: list[str] = Field(default_factory=list)


class NpcMemoryEntry(BaseModel):
    """Dynamic memory snippet of NPC interactions."""

    summary_id: Annotated[str, Field(min_length=1)]
    impact: Annotated[str, Field(min_length=1)]
    recorded_at: datetime | None = None


class NpcProfile(BaseModel):
    """Combined static and dynamic profile of a non-player character."""

    npc_id: Annotated[str, Field(min_length=1)]
    name: Annotated[str, Field(min_length=1)]
    archetype: Annotated[str, Field(min_length=1)]
    voice_tts: str | None = None
    secrets: list[str] = Field(default_factory=list)
    lore_refs: list[str] = Field(default_factory=list)
    disposition: dict[str, int] = Field(default_factory=dict)
    memory: list[NpcMemoryEntry] = Field(default_factory=list)
    version: Annotated[str, Field(min_length=1)] = "1.0.0"


class ArtCard(BaseModel):
    """Media artifact (image/audio) with metadata usable for retrieval."""

    image_id: Annotated[str, Field(min_length=1)]
    scene_id: Annotated[str, Field(min_length=1)]
    cdn_url: HttpUrl
    prompt_text: Annotated[str, Field(min_length=1)]
    entities: dict[str, list[str]] = Field(default_factory=dict)
    visual_tags: list[str] = Field(default_factory=list)
    style_preset: str | None = None
    seed: int | None = None
    moderation_safe: bool = True
    provider: str | None = None


class KnowledgeItem(BaseModel):
    """Generic knowledge chunk used for search indexing."""

    item_id: Annotated[str, Field(min_length=1)]
    domain: Literal["scene", "npc", "art", "lore"]
    content: Annotated[str, Field(min_length=1)]
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

