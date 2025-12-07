import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "memory37-graph" / "src"))
sys.path.append(str(ROOT / "memory37" / "src"))

from memory37.versioning import KnowledgeVersion, KnowledgeVersionRegistry  # type: ignore  # noqa: E402
from memory37.domain import KnowledgeItem, NpcProfile  # type: ignore  # noqa: E402
from memory37_graph import (  # type: ignore  # noqa: E402
    GraphClient,
    GraphConfig,
    GraphIngest,
    GraphRagQueries,
    KnowledgeVersionRef,
    SceneGraphContextRequest,
)


def test_inmemory_ingest_and_scene_context() -> None:
    registry = KnowledgeVersionRegistry()
    registry.register(KnowledgeVersion(id="kv_test", semver="1.0.0", kind="lore", status="latest"))

    client = GraphClient(config=None, version_registry=registry)
    ingest = GraphIngest(graph_client=client, version_registry=registry)
    queries = GraphRagQueries(graph_client=client, ingest=ingest)

    lore_chunks = [
        KnowledgeItem(item_id="lore::tower", domain="lore", content="Ancient tower", metadata={"tags": "ruins"}),
        KnowledgeItem(item_id="lore::forest", domain="lore", content="Mystic forest", metadata={"tags": "nature"}),
    ]
    ingest.ingest_lore(KnowledgeVersionRef(alias="lore_latest"), lore_chunks)

    npc = NpcProfile(
        npc_id="npc_1",
        name="Li Shen",
        archetype="ronin",
        voice_tts=None,
        secrets=[],
        lore_refs=["lore::tower"],
        disposition={"faction::ronin": 1},
        memory=[],
    )
    ingest.ingest_npc_profiles(KnowledgeVersionRef(alias="lore_latest"), [npc])

    ctx = queries.scene_context(
        SceneGraphContextRequest(
            scene_id="scn_1",
            campaign_id="cmp_1",
            party_id="pty_1",
            version=KnowledgeVersionRef(alias="lore_latest"),
        )
    )

    assert ctx.nodes, "Nodes should not be empty after ingest"
    assert any(node["id"] == "npc::npc_1" for node in ctx.nodes)
    assert ctx.relations or ctx.summary
