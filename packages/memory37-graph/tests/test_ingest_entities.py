import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "memory37-graph" / "src"))
sys.path.append(str(ROOT / "memory37" / "src"))

from memory37.versioning import KnowledgeVersionRegistry, KnowledgeVersion  # type: ignore  # noqa: E402
from memory37_graph import GraphClient, GraphIngest, KnowledgeVersionRef  # type: ignore  # noqa: E402


def test_ingest_entities_generic() -> None:
    registry = KnowledgeVersionRegistry()
    registry.register(KnowledgeVersion(id="kv_test", semver="1.0.0", kind="lore", status="latest"))
    client = GraphClient(config=None, version_registry=registry)
    ingest = GraphIngest(graph_client=client, version_registry=registry)

    facts = [
        {
            "id": "loc::forest",
            "type": "Location",
            "properties": {"tags": ["nature"], "importance": 5},
            "relations": [
                {"to": "faction::wardens", "type": "MEMBER_OF", "direction": "out", "weight": 0.8},
            ],
        },
        {
            "id": "quest::moon",
            "type": "Quest",
            "properties": {"difficulty": "medium", "importance": 10},
            "relations": [
                {"to": "loc::forest", "type": "INVOLVED_IN", "direction": "out"},
            ],
        },
    ]

    ingest.ingest_entities(KnowledgeVersionRef(alias="lore_latest"), facts)
    nodes = ingest.nodes("kv_test")
    rels = ingest.relations("kv_test")

    assert any(n.id == "loc::forest" for n in nodes)
    assert any(r.to_id == "loc::forest" and r.type == "INVOLVED_IN" for r in rels)
