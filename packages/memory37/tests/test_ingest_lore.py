from __future__ import annotations

from pathlib import Path

from memory37.ingest import load_knowledge_items_from_yaml


def test_load_lore_items_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
scenes:
  - id: scn_001
    title: Moon Bridge
    summary: Ancient bridge in mist
    tags: [moon, bridge]
    timeline: [Party arrives, Ronin tests vows]
npcs:
  - id: npc_ronin
    name: Li Shen
    archetype: ronin
    summary: Swordsman testing intent
art:
  - id: art_bridge
    prompt: moonlit misty bridge illustration
    tags: [moon, mist, ronin]
    entities:
      npc: [npc_ronin]
lore:
  - id: lore_reward_moon_token
    title: reward:moon_token
    body: A token that grants safe passage at moon bridges.
    tags: [reward, token]
    related:
      scene: scn_001
      npc: npc_ronin
"""

    file_path = tmp_path / "knowledge.yaml"
    file_path.write_text(yaml_content, encoding="utf-8")

    items = load_knowledge_items_from_yaml(file_path)

    # Ensure lore item present
    lore_items = [it for it in items if it.item_id == "lore::lore_reward_moon_token"]
    assert len(lore_items) == 1
    lore = lore_items[0]
    assert lore.domain == "lore"
    assert "reward:moon_token" in lore.content
    # Metadata checks
    assert lore.metadata.get("lore_id") == "lore_reward_moon_token"
    assert lore.metadata.get("tags") == "reward,token"
    assert lore.metadata.get("related") == "scene:scn_001,npc:npc_ronin"

