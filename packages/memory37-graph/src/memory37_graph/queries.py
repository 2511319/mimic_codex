from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .client import GraphClient, KnowledgeVersionRef
from .ingest import GraphIngest
from .schema import GraphNode, GraphRelation


@dataclass
class SceneGraphContextRequest:
    scene_id: str
    campaign_id: str
    party_id: str
    version: KnowledgeVersionRef
    max_depth: int = 1
    max_nodes: int = 100


@dataclass
class SceneGraphContext:
    nodes: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    summary: str = ""
    degraded: bool = False


class GraphRagQueries:
    """Запросы GraphRAG поверх GraphIngest (in-memory)."""

    def __init__(self, graph_client: GraphClient, ingest: GraphIngest) -> None:
        self._graph_client = graph_client
        self._ingest = ingest

    def scene_context(self, req: SceneGraphContextRequest) -> SceneGraphContext:
        version_id = self._graph_client.resolve_version_id(req.version)
        if self._graph_client.has_driver():
            try:
                return self._scene_context_neo4j(req, version_id)
            except Exception:
                # graceful degradation
                pass
        nodes = self._ingest.nodes(version_id)
        relations = self._ingest.relations(version_id)

        filtered_nodes = self._filter_nodes(nodes, req)
        filtered_ids = {n.id for n in filtered_nodes}
        filtered_relations = [rel for rel in relations if rel.from_id in filtered_ids and rel.to_id in filtered_ids]

        summary = f"{len(filtered_nodes)} nodes, {len(filtered_relations)} relations for scene {req.scene_id}"
        return SceneGraphContext(
            nodes=[self._node_to_dict(node) for node in filtered_nodes],
            relations=[self._relation_to_dict(rel) for rel in filtered_relations],
            summary=summary,
            degraded=not self._graph_client.has_driver(),
        )

    def npc_social_context(self, npc_id: str, party_id: str, version: KnowledgeVersionRef) -> SceneGraphContext:
        version_id = self._graph_client.resolve_version_id(version)
        if self._graph_client.has_driver():
            try:
                cypher = """
                MATCH (npc:NPC {id:$npc_id, knowledge_version_id:$vid})
                OPTIONAL MATCH (npc)-[r:RELATIONSHIP]-(other)
                  WHERE r.knowledge_version_id=$vid
                OPTIONAL MATCH (npc)-[m:MEMBER_OF]->(f:Faction) WHERE m.knowledge_version_id=$vid
                WITH collect(DISTINCT npc)+collect(DISTINCT other)+collect(DISTINCT f) as nodes,
                     collect(DISTINCT r)+collect(DISTINCT m) as rels
                RETURN nodes, rels
                """
                with self._graph_client.session(version) as session:
                    records = list(session.run(cypher, {"npc_id": f"npc::{npc_id}", "vid": version_id}))
                nodes, rels = self._extract_nodes_rels(records)
                summary = f"NPC {npc_id} social context ({len(nodes)} nodes/{len(rels)} rels)"
                return SceneGraphContext(nodes=nodes, relations=rels, summary=summary, degraded=False)
            except Exception:
                pass
        req = SceneGraphContextRequest(scene_id="*", campaign_id="*", party_id=party_id, version=version)
        ctx = self.scene_context(req)
        ctx.summary = f"NPC {npc_id} social view with party {party_id}"
        return ctx

    def quest_graph_context(self, quest_id: str, version: KnowledgeVersionRef) -> SceneGraphContext:
        version_id = self._graph_client.resolve_version_id(version)
        if self._graph_client.has_driver():
            try:
                cypher = """
                MATCH (q:Quest {id:$qid, knowledge_version_id:$vid})
                OPTIONAL MATCH (q)-[r:INVOLVED_IN|BLOCKS|UNLOCKS|CAUSES]-(n)
                  WHERE r.knowledge_version_id=$vid
                RETURN collect(DISTINCT q)+collect(DISTINCT n) as nodes, collect(DISTINCT r) as rels
                """
                with self._graph_client.session(version) as session:
                    records = list(session.run(cypher, {"qid": f"quest::{quest_id}", "vid": version_id}))
                nodes, rels = self._extract_nodes_rels(records)
                summary = f"Quest {quest_id} context ({len(nodes)} nodes/{len(rels)} rels)"
                return SceneGraphContext(nodes=nodes, relations=rels, summary=summary, degraded=False)
            except Exception:
                pass
        req = SceneGraphContextRequest(scene_id=quest_id, campaign_id="*", party_id="*", version=version)
        ctx = self.scene_context(req)
        ctx.summary = f"Quest {quest_id} context"
        return ctx

    def causal_chain(
        self,
        from_event_id: str,
        to_event_id: str | None,
        version: KnowledgeVersionRef,
        max_hops: int = 4,
    ) -> SceneGraphContext:
        version_id = self._graph_client.resolve_version_id(version)
        if self._graph_client.has_driver():
            try:
                cypher = """
                MATCH (src:Event {id:$src, knowledge_version_id:$vid})
                MATCH (dst:Event {id:$dst, knowledge_version_id:$vid})
                CALL apoc.algo.dijkstra(src, dst, 'CAUSES|BLOCKS|UNLOCKS', 'weight') YIELD path, weight
                RETURN nodes(path) as nodes, relationships(path) as rels, weight
                LIMIT 1
                """
                params = {"src": from_event_id, "dst": to_event_id or from_event_id, "vid": version_id}
                with self._graph_client.session(version) as session:
                    records = list(session.run(cypher, params))
                nodes, rels = self._extract_nodes_rels(records)
                summary = f"Causal chain from {from_event_id} to {to_event_id or 'any'}"
                return SceneGraphContext(nodes=nodes, relations=rels, summary=summary, degraded=False)
            except Exception:
                pass
        req = SceneGraphContextRequest(scene_id=from_event_id, campaign_id="*", party_id="*", version=version, max_depth=max_hops)
        ctx = self.scene_context(req)
        ctx.summary = f"Causal chain from {from_event_id} to {to_event_id or 'any'}"
        return ctx

    def _scene_context_neo4j(self, req: SceneGraphContextRequest, version_id: str) -> SceneGraphContext:
        cypher = """
        MATCH (s {knowledge_version_id:$vid})-[:INVOLVED_IN|APPEARED_IN|LOCATED_IN*1..2]-(n)
        WHERE s.id = $scene_id
        WITH DISTINCT n LIMIT $max_nodes
        OPTIONAL MATCH (n)-[r]-(m) WHERE r.knowledge_version_id=$vid AND m.knowledge_version_id=$vid
        RETURN collect(DISTINCT n) as nodes, collect(DISTINCT r) as rels
        """
        with self._graph_client.session(req.version) as session:
            records = list(session.run(cypher, {"scene_id": req.scene_id, "vid": version_id, "max_nodes": req.max_nodes}))
        nodes_res, rels_res = self._extract_nodes_rels(records)
        summary = f"{len(nodes_res)} nodes, {len(rels_res)} relations for scene {req.scene_id}"
        return SceneGraphContext(nodes=nodes_res, relations=rels_res, summary=summary, degraded=False)

    @staticmethod
    def _extract_nodes_rels(records: list[dict]) -> tuple[list[dict], list[dict]]:
        nodes_res: list[dict] = []
        rels_res: list[dict] = []
        if not records:
            return nodes_res, rels_res
        data = records[0]
        for n in data.get("nodes", []):
            nodes_res.append(
                {
                    "id": n.get("id"),
                    "type": list(n.labels)[0] if hasattr(n, "labels") else n.get("type", "Unknown"),
                    "knowledgeVersionId": n.get("knowledge_version_id"),
                    "properties": dict(n) if hasattr(n, "items") else {},
                }
            )
        for r in data.get("rels", []):
            rels_res.append(
                {
                    "from": r.start_node.get("id") if hasattr(r, "start_node") else None,
                    "to": r.end_node.get("id") if hasattr(r, "end_node") else None,
                    "type": r.type if hasattr(r, "type") else r.get("type", ""),
                    "knowledgeVersionId": r.get("knowledge_version_id") if hasattr(r, "get") else None,
                    "properties": dict(r) if hasattr(r, "items") else {},
                }
            )
        return nodes_res, rels_res

    def _filter_nodes(self, nodes: Iterable[GraphNode], req: SceneGraphContextRequest) -> list[GraphNode]:
        sorted_nodes = sorted(nodes, key=lambda n: n.properties.get("importance", 0), reverse=True)
        return sorted_nodes[: req.max_nodes]

    @staticmethod
    def _node_to_dict(node: GraphNode) -> dict:
        return {
            "id": node.id,
            "type": node.type,
            "knowledgeVersionId": node.knowledge_version_id,
            "properties": node.properties,
        }

    @staticmethod
    def _relation_to_dict(rel: GraphRelation) -> dict:
        return {
            "from": rel.from_id,
            "to": rel.to_id,
            "type": rel.type,
            "knowledgeVersionId": rel.knowledge_version_id,
            "properties": rel.properties,
        }
