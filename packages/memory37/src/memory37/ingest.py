"""Helpers for loading knowledge items from files and runtime snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import yaml

from .domain import ArtCard, KnowledgeItem, NpcProfile, SceneState


def load_knowledge_items_from_yaml(path: str | Path) -> list[KnowledgeItem]:
    """Load knowledge items from YAML file with scenes, NPCs, and art sections."""

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Knowledge source not found: {file_path}")

    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Knowledge YAML root must be a mapping")

    items: list[KnowledgeItem] = []
    for scene in data.get("scenes", []) or []:
        items.append(_scene_to_knowledge(scene))
    for npc in data.get("npcs", []) or []:
        items.append(_npc_to_knowledge(npc))
    for art in data.get("art", []) or []:
        items.append(_art_to_knowledge(art))
    for lore in data.get("lore", []) or []:
        items.append(_lore_to_knowledge(lore))

    return items


def build_runtime_items(
    *,
    scenes: Iterable[SceneState] = (),
    npcs: Iterable[NpcProfile] = (),
    art_cards: Iterable[ArtCard] = (),
) -> list[KnowledgeItem]:
    """Convert runtime domain objects into knowledge items for indexing."""

    items: list[KnowledgeItem] = []
    for scene in scenes:
        chronology = " | ".join(entry.summary for entry in scene.chronology)
        relations = ", ".join(f"{delta.source_id}->{delta.target_id}:{delta.delta}" for delta in scene.relations_delta)
        content = f"Scene {scene.title}: {scene.summary}. Timeline: {chronology}. Relations: {relations}."
        items.append(
            KnowledgeItem(
                item_id=f"scene::{scene.scene_id}",
                domain="scene",
                content=content,
                metadata={"campaign_id": scene.campaign_id, "tags": ",".join(scene.tags)},
            )
        )

    for npc in npcs:
        disposition = ", ".join(f"{k}:{v}" for k, v in npc.disposition.items())
        memory = "; ".join(entry.impact for entry in npc.memory)
        content = f"NPC {npc.name} ({npc.archetype}). Disposition: {disposition}. Memory: {memory}."
        items.append(
            KnowledgeItem(
                item_id=f"npc::{npc.npc_id}",
                domain="npc",
                content=content,
                metadata={"voice_tts": npc.voice_tts or "", "secrets": ",".join(npc.secrets)},
            )
        )

    for card in art_cards:
        tags = ",".join(card.visual_tags)
        entities = ",".join(f"{key}:{','.join(vals)}" for key, vals in card.entities.items())
        content = f"ArtCard {card.image_id}: {card.prompt_text}. Tags: {tags}. Entities: {entities}."
        items.append(
            KnowledgeItem(
                item_id=f"art::{card.image_id}",
                domain="art",
                content=content,
                metadata={"scene_id": card.scene_id, "cdn_url": str(card.cdn_url)},
            )
        )

    return items


def _scene_to_knowledge(data: dict) -> KnowledgeItem:
    scene_id = data.get("id") or data.get("scene_id")
    summary = data.get("summary", "")
    title = data.get("title", scene_id)
    tags = data.get("tags", [])
    timeline = data.get("timeline", [])
    content = f"Scene {title}: {summary}. Timeline: {' | '.join(str(item) for item in timeline)}."
    metadata = {"scene_id": scene_id, "tags": ",".join(tags)}
    return KnowledgeItem(item_id=f"scene::{scene_id}", domain="scene", content=content, metadata=metadata)


def _npc_to_knowledge(data: dict) -> KnowledgeItem:
    npc_id = data.get("id") or data.get("npc_id")
    name = data.get("name", npc_id)
    archetype = data.get("archetype", "")
    summary = data.get("summary", "")
    content = f"NPC {name} ({archetype}). {summary}"
    metadata = {"npc_id": npc_id, "voice_tts": data.get("voice_tts", "")}
    return KnowledgeItem(item_id=f"npc::{npc_id}", domain="npc", content=content, metadata=metadata)


def _art_to_knowledge(data: dict) -> KnowledgeItem:
    image_id = data.get("id") or data.get("image_id")
    prompt = data.get("prompt") or data.get("prompt_text", "")
    tags = data.get("tags", [])
    entities = data.get("entities", {})
    entities_str = ",".join(f"{k}:{','.join(vs)}" for k, vs in entities.items())
    content = f"Art {image_id}: {prompt}. Entities: {entities_str}."
    metadata = {"image_id": image_id, "tags": ",".join(tags)}
    return KnowledgeItem(item_id=f"art::{image_id}", domain="art", content=content, metadata=metadata)


def _lore_to_knowledge(data: dict) -> KnowledgeItem:
    """Convert a lore/reward entry to KnowledgeItem.

    Expected minimal structure:
      { id: string, title: string, body: string, tags: string[], related?: { scene?: string, npc?: string } }
    """

    lore_id = data.get("id") or data.get("lore_id")
    title = data.get("title", lore_id)
    body = data.get("body", "")
    tags = data.get("tags", []) or []
    related = data.get("related", {}) or {}

    related_bits: list[str] = []
    scene_ref = related.get("scene")
    npc_ref = related.get("npc")
    if scene_ref:
        related_bits.append(f"scene:{scene_ref}")
    if npc_ref:
        related_bits.append(f"npc:{npc_ref}")
    related_str = ",".join(related_bits)

    content = f"{title}: {body}"
    metadata = {"lore_id": lore_id, "tags": ",".join(tags)}
    if related_str:
        metadata["related"] = related_str

    return KnowledgeItem(item_id=f"lore::{lore_id}", domain="lore", content=content, metadata=metadata)
