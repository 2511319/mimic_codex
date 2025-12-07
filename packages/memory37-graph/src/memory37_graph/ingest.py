from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Mapping, Any

from memory37.domain import NpcProfile, KnowledgeItem
from memory37.versioning import KnowledgeVersionRegistry

from .client import GraphClient, KnowledgeVersionRef
from .schema import GraphNode, GraphRelation, GraphFact, validate_label, validate_rel_type


@dataclass
class InMemoryGraph:
    """Простейший in-memory граф, разделённый по version_id."""

    nodes: dict[str, dict[str, GraphNode]] = field(default_factory=dict)
    relations: dict[str, list[GraphRelation]] = field(default_factory=dict)

    def upsert_node(self, version_id: str, node: GraphNode) -> None:
        self.nodes.setdefault(version_id, {})[node.id] = node

    def add_relation(self, version_id: str, rel: GraphRelation) -> None:
        self.relations.setdefault(version_id, []).append(rel)

    def get_nodes(self, version_id: str) -> list[GraphNode]:
        return list(self.nodes.get(version_id, {}).values())

    def get_relations(self, version_id: str) -> list[GraphRelation]:
        return list(self.relations.get(version_id, []))


class GraphIngest:
    """Идемпотентный ingest данных в граф (Neo4j или in-memory)."""

    def __init__(
        self,
        graph_client: GraphClient,
        version_registry: KnowledgeVersionRegistry,
        memory_graph: InMemoryGraph | None = None,
        *,
        episode_ttl_days: int = 180,
        npc_relation_ttl_days: int = 180,
        quest_relation_ttl_days: int = 365,
    ) -> None:
        self._graph_client = graph_client
        self._version_registry = version_registry
        self._memory = memory_graph or InMemoryGraph()
        self._episode_ttl_days = episode_ttl_days
        self._npc_relation_ttl_days = npc_relation_ttl_days
        self._quest_relation_ttl_days = quest_relation_ttl_days

    def ingest_lore(self, version_ref: KnowledgeVersionRef, chunks: Iterable[KnowledgeItem]) -> None:
        version_id = self._graph_client.resolve_version_id(version_ref)
        for chunk in chunks:
            node = GraphNode(
                id=chunk.item_id,
                type="Concept",
                knowledge_version_id=version_id,
                properties={"tags": chunk.metadata.get("tags", "").split(",")},
            )
            self._memory.upsert_node(version_id, node)
            self._upsert_node_neo4j(node)

    def ingest_npc_profiles(self, version_ref: KnowledgeVersionRef, profiles: Iterable[NpcProfile]) -> None:
        version_id = self._graph_client.resolve_version_id(version_ref)
        for profile in profiles:
            node = GraphNode(
                id=f"npc::{profile.npc_id}",
                type="NPC",
                knowledge_version_id=version_id,
                properties={
                    "name": profile.name,
                    "archetype": profile.archetype,
                    "voice_tts": profile.voice_tts,
                    "tags": profile.lore_refs,
                },
                expires_at=None,
            )
            self._memory.upsert_node(version_id, node)
            self._upsert_node_neo4j(node)
            for faction_id, delta in profile.disposition.items():
                rel = GraphRelation(
                    from_id=node.id,
                    to_id=f"faction::{faction_id}",
                    type="RELATIONSHIP",
                    knowledge_version_id=version_id,
                    properties={"weight": float(delta), "source": "npc_profile"},
                    expires_at=self._expires_in_days(self._npc_relation_ttl_days),
                )
                self._memory.add_relation(version_id, rel)
                self._upsert_relation_neo4j(rel)

    def ingest_episodes(self, version_ref: KnowledgeVersionRef, episodes: Iterable[Mapping[str, object]]) -> None:
        version_id = self._graph_client.resolve_version_id(version_ref)
        for ep in episodes:
            summary_id = str(ep.get("summary_id") or ep.get("id") or ep.get("episode_id"))
            node = GraphNode(
                id=f"episode::{summary_id}",
                type="Episode",
                knowledge_version_id=version_id,
                properties={"scene_id": ep.get("scene_id"), "campaign_id": ep.get("campaign_id")},
                expires_at=self._expires_in_days(self._episode_ttl_days),
            )
            self._memory.upsert_node(version_id, node)
            self._upsert_node_neo4j(node)

    def apply_episode_delta(self, version_ref: KnowledgeVersionRef, summary: Mapping[str, object]) -> None:
        version_id = self._graph_client.resolve_version_id(version_ref)
        summary_id = str(summary.get("summary_id") or summary.get("id"))
        rels = summary.get("relations_delta") or []
        for rel in rels:
            source = rel.get("source_id")
            target = rel.get("target_id")
            if not source or not target:
                continue
            relation = GraphRelation(
                from_id=source,
                to_id=target,
                type=validate_rel_type("RELATIONSHIP"),
                knowledge_version_id=version_id,
                properties={
                    "weight": float(rel.get("delta", 0)),
                    "source": "episode",
                    "summary_id": summary_id,
                },
                expires_at=self._expires_in_days(self._npc_relation_ttl_days),
            )
            self._memory.add_relation(version_id, relation)
            self._upsert_relation_neo4j(relation)

    def ingest_entities(self, version_ref: KnowledgeVersionRef, facts: Iterable[Mapping[str, Any]]) -> None:
        """Универсальный ingest для Location/Faction/Quest/Item/Event/Concept."""

        version_id = self._graph_client.resolve_version_id(version_ref)
        for fact in facts:
            node = GraphNode(
                id=str(fact["id"]),
                type=validate_label(str(fact.get("type", "Concept"))),
                knowledge_version_id=version_id,
                properties={**(fact.get("properties", {}) or {}), "importance": (fact.get("properties", {}) or {}).get("importance", 0)},
                expires_at=fact.get("expires_at"),
            )
            self._memory.upsert_node(version_id, node)
            self._upsert_node_neo4j(node)

            for rel in fact.get("relations", []) or []:
                default_ttl = self._quest_relation_ttl_days if str(rel.get("type", "")).upper() in {"BLOCKS", "UNLOCKS", "CAUSES"} else None
                expires_at = rel.get("expires_at") or self._expires_in_days(default_ttl)
                relation = GraphRelation(
                    from_id=node.id if rel.get("direction", "out") == "out" else str(rel.get("to")),
                    to_id=str(rel.get("to")) if rel.get("direction", "out") == "out" else node.id,
                    type=validate_rel_type(str(rel.get("type", "RELATIONSHIP"))),
                    knowledge_version_id=version_id,
                    properties={k: v for k, v in rel.items() if k not in {"to", "type", "direction", "expires_at"}},
                    expires_at=expires_at,
                )
                self._memory.add_relation(version_id, relation)
                self._upsert_relation_neo4j(relation)

    # Утилиты для GraphRagQueries
    def nodes(self, version_id: str) -> list[GraphNode]:
        return self._memory.get_nodes(version_id)

    def relations(self, version_id: str) -> list[GraphRelation]:
        return self._memory.get_relations(version_id)

    def cleanup_expired(self) -> None:
        """Удаляет просроченные узлы/связи (TTL)."""

        # In-memory cleanup
        for vid, nodes in list(self._memory.nodes.items()):
            self._memory.nodes[vid] = {nid: n for nid, n in nodes.items() if not n.expires_at}
        for vid, rels in list(self._memory.relations.items()):
            self._memory.relations[vid] = [r for r in rels if not r.expires_at]

        # Neo4j cleanup (if available)
        if self._graph_client.has_driver():
            with self._graph_client.session(KnowledgeVersionRef(alias="lore_latest")) as session:
                session.run(
                    """
                    MATCH (n)
                    WHERE n.expires_at IS NOT NULL AND datetime(n.expires_at) < datetime()
                    DETACH DELETE n
                    """,
                    {},
                )
                session.run(
                    """
                    MATCH ()-[r]-()
                    WHERE r.expires_at IS NOT NULL AND datetime(r.expires_at) < datetime()
                    DELETE r
                    """,
                    {},
                )

    def _upsert_node_neo4j(self, node: GraphNode) -> None:
        if not self._graph_client.has_driver():
            return
        with self._graph_client.session(KnowledgeVersionRef(version_id=node.knowledge_version_id)) as session:
            session.run(
                f"""
                MERGE (n:{validate_label(node.type)} {{id:$id, knowledge_version_id:$vid}})
                SET n += $props
                SET n.expires_at = $expires_at
                """,
                {
                    "id": node.id,
                    "vid": node.knowledge_version_id,
                    "props": {**node.properties},
                    "expires_at": node.expires_at,
                },
            )

    def _upsert_relation_neo4j(self, rel: GraphRelation) -> None:
        if not self._graph_client.has_driver():
            return
        with self._graph_client.session(KnowledgeVersionRef(version_id=rel.knowledge_version_id)) as session:
            session.run(
                f"""
                MERGE (a {{id:$from_id, knowledge_version_id:$vid}})
                MERGE (b {{id:$to_id, knowledge_version_id:$vid}})
                MERGE (a)-[r:{validate_rel_type(rel.type)} {{knowledge_version_id:$vid}}]->(b)
                SET r += $props
                SET r.expires_at = $expires_at
                """,
                {
                    "from_id": rel.from_id,
                    "to_id": rel.to_id,
                    "vid": rel.knowledge_version_id,
                    "props": {**rel.properties},
                    "expires_at": rel.expires_at,
                },
            )

    def _expires_in_days(self, days: int | None) -> str | None:
        if not days or days <= 0:
            return None
        return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
