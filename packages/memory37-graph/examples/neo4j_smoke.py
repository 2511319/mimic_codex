"""
Простой smoke-скрипт для Neo4j GraphRAG.

Usage:
  set NEO4J_URI=bolt://localhost:7687
  set NEO4J_USER=neo4j
  set NEO4J_PASSWORD=password
  python packages/memory37-graph/examples/neo4j_smoke.py
"""

from __future__ import annotations

import os

from memory37 import KnowledgeVersion, KnowledgeVersionRegistry
from memory37_graph import (
    GraphClient,
    GraphConfig,
    GraphIngest,
    GraphRagQueries,
    KnowledgeVersionRef,
    SceneGraphContextRequest,
)


def main() -> None:
    uri = os.environ.get("NEO4J_URI")
    user = os.environ.get("NEO4J_USER")
    password = os.environ.get("NEO4J_PASSWORD")
    if not (uri and user and password):
        raise SystemExit("NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD required")

    registry = KnowledgeVersionRegistry()
    registry.register(KnowledgeVersion(id="kv_smoke", semver="1.0.0", kind="lore", status="latest"))

    client = GraphClient(GraphConfig(uri=uri, user=user, password=password, database=os.environ.get("NEO4J_DATABASE")), registry)
    client.run_default_migrations()

    ingest = GraphIngest(client, registry)
    queries = GraphRagQueries(client, ingest)

    ingest.ingest_entities(
        KnowledgeVersionRef(alias="lore_latest"),
        [
            {
                "id": "loc::forest",
                "type": "Location",
                "properties": {"importance": 5, "tags": ["forest"]},
            },
            {
                "id": "quest::moon",
                "type": "Quest",
                "properties": {"importance": 10},
                "relations": [{"to": "loc::forest", "type": "INVOLVED_IN", "direction": "out"}],
            },
        ],
    )

    ctx = queries.scene_context(
        SceneGraphContextRequest(
            scene_id="quest::moon",
            campaign_id="cmp",
            party_id="pty",
            version=KnowledgeVersionRef(alias="lore_latest"),
        )
    )
    print("Summary:", ctx.summary)
    print("Nodes:", len(ctx.nodes), "Relations:", len(ctx.relations), "Degraded:", ctx.degraded)


if __name__ == "__main__":
    main()
