from pathlib import Path

import pytest

from datetime import datetime

from memory37.domain import ArtCard, NpcMemoryEntry, NpcProfile, RelationDelta, SceneChronicleEntry, SceneState
from memory37.ingest import build_runtime_items, load_knowledge_items_from_yaml


def test_load_knowledge_items_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
scenes:
  - id: scn_001
    title: Moon Bridge
    summary: Ancient ruins under the moon
    tags: [moon, ruins]
    timeline:
      - Party arrives at bridge
npcs:
  - id: npc_001
    name: Li Shen
    archetype: ronin
    summary: Wandering swordsman
art:
  - id: art_001
    prompt: moonlit bridge illustration
    tags: [moon, bridge]
    entities:
      npc: [npc_001]
"""
    file_path = tmp_path / "knowledge.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")

    items = load_knowledge_items_from_yaml(file_path)

    ids = {item.item_id for item in items}
    assert ids == {"scene::scn_001", "npc::npc_001", "art::art_001"}


def test_build_runtime_items_from_domain_objects() -> None:
    scene = SceneState(
        scene_id="scn_002",
        campaign_id="cmp_001",
        title="Foggy Market",
        summary="Party talks to merchant",
        chronology=[SceneChronicleEntry(timestamp=datetime.utcnow(), summary="Arrival")],
        relations_delta=[RelationDelta(source_id="party", target_id="npc_merchant", delta=1, reason="helped")],
        tags=["market", "fog"],
    )

    npc = NpcProfile(
        npc_id="npc_merchant",
        name="Yara",
        archetype="merchant",
        voice_tts="female_warm",
        secrets=["hidden_debt"],
        disposition={"party": 2},
        memory=[NpcMemoryEntry(summary_id="sum_1", impact="trust+1")],
    )

    art = ArtCard(
        image_id="art_002",
        scene_id="scn_002",
        cdn_url="https://cdn.example/art_002.webp",
        prompt_text="foggy market stall",
        entities={"npc": ["npc_merchant"]},
        visual_tags=["fog", "market"],
    )

    items = build_runtime_items(scenes=[scene], npcs=[npc], art_cards=[art])

    ids = {item.item_id for item in items}
    assert ids == {"scene::scn_002", "npc::npc_merchant", "art::art_002"}
    scene_item = next(item for item in items if item.item_id == "scene::scn_002")
    assert "Foggy Market" in scene_item.content
