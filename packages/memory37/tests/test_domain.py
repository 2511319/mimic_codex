from datetime import datetime

from memory37.domain import ArtCard, KnowledgeItem, NpcMemoryEntry, NpcProfile, RelationDelta, SceneChronicleEntry, SceneState


def test_scene_state_accepts_chronology_and_relations() -> None:
    event = SceneChronicleEntry(timestamp=datetime.utcnow(), summary="NPC встречает партию")
    relation = RelationDelta(source_id="npc_LiShen", target_id="party", delta=1, reason="kept promise")

    scene = SceneState(
        scene_id="scn_001",
        campaign_id="cmp_001",
        title="Moonlit Bridge",
        summary="Партия встретила Ли Шэня на мосту в туманную ночь",
        chronology=[event],
        relations_delta=[relation],
        tags=["moonlight", "bridge"]
    )

    assert scene.chronology[0].summary == "NPC встречает партию"
    assert scene.relations_delta[0].delta == 1


def test_npc_profile_merges_static_and_dynamic_fields() -> None:
    memory = NpcMemoryEntry(summary_id="sum_001", impact="trust+1")

    profile = NpcProfile(
        npc_id="npc_LiShen",
        name="Ли Шэнь",
        archetype="ronin",
        voice_tts="asian_male_light_smoke",
        secrets=["scar_left_cheek_reason"],
        lore_refs=["lore_ronin_code"],
        disposition={"party_id:pty_001": 2},
        memory=[memory]
    )

    assert profile.disposition["party_id:pty_001"] == 2
    assert profile.memory[0].impact == "trust+1"


def test_art_card_validates_url() -> None:
    card = ArtCard(
        image_id="img_001",
        scene_id="scn_001",
        cdn_url="https://cdn.example/scene.webp",
        prompt_text="moonlit bridge, mist, ronin",
        entities={"npc": ["npc_LiShen"]},
        visual_tags=["moonlight", "mist"],
        style_preset="ukiyo-e-modern",
        seed=12345,
        moderation_safe=True
    )

    assert str(card.cdn_url).endswith("scene.webp")


def test_knowledge_item_defaults_metadata() -> None:
    item = KnowledgeItem(item_id="kn_001", domain="lore", content="Legend about the bridge")

    assert item.metadata == {}
    assert item.created_at <= datetime.utcnow()
