"""Импорт контента из D:\\project\\Lore в Memory37 (pgvector) и Neo4j."""

from __future__ import annotations

import asyncio
import argparse
import json
import os
from pathlib import Path
from typing import Iterable

try:
    import psycopg  # type: ignore
except Exception:  # pragma: no cover - опционально для pgvector
    psycopg = None  # type: ignore[assignment]

from memory37.embedding import OpenAIEmbeddingProvider, TokenFrequencyEmbeddingProvider
from memory37.stores.pgvector_store import InMemoryVectorStore, PgVectorWrapper
from memory37.types import Chunk
from memory37.versioning import KnowledgeVersion, KnowledgeVersionRegistry

try:  # pragma: no cover - граф опционален
    from memory37_graph import GraphClient, GraphConfig, GraphIngest, KnowledgeVersionRef
except Exception:
    GraphClient = None  # type: ignore
    GraphConfig = None  # type: ignore
    GraphIngest = None  # type: ignore
    KnowledgeVersionRef = None  # type: ignore


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_env_key_if_missing() -> None:
    """Подхватывает OPENAI_API_KEY из локального .env, если не задан в окружении."""

    if os.environ.get("OPENAI_API_KEY"):
        return
    env_path = Path(".env")
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            if key.strip() == "OPENAI_API_KEY" and val.strip():
                os.environ["OPENAI_API_KEY"] = val.strip()
                break
    except Exception:
        return


def _embedding_provider(use_openai: bool, model: str | None):
    if use_openai:
        try:
            return OpenAIEmbeddingProvider(model=model)
        except Exception:
            pass
    return TokenFrequencyEmbeddingProvider()


def _build_store(dsn: str | None, provider, embedding_model: str | None):
    if dsn and psycopg is not None:
        return PgVectorWrapper(lambda: psycopg.connect(dsn), embedding_provider=provider, embedding_model=embedding_model)
    return InMemoryVectorStore(embedding_provider=provider, embedding_model=embedding_model)


def collect_chunks(content_root: Path, version_id: str) -> list[Chunk]:
    chunks: list[Chunk] = []
    # Lore
    for path in content_root.glob("lore/**/*.json"):
        data = _load_json(path)
        lore_id = data.get("id") or path.stem
        body = data.get("body") or {}
        text = f"{body.get('name','')}: {body.get('description','')}"
        meta = {
            "tags": ",".join(data.get("tags", [])),
            "campaign_id": data.get("campaign_id", ""),
            "lore_kind": path.parts[-2] if len(path.parts) >= 2 else "",
            "knowledge_version_id": version_id,
        }
        chunks.append(Chunk(id=f"lore::{lore_id}", domain="lore", text=text, metadata=meta, payload={}))

    # NPC
    for path in content_root.glob("npc/**/*.json"):
        data = _load_json(path)
        npc_id = data.get("npcId") or path.stem
        summary = data.get("description", "")
        personality = data.get("personality", {})
        text = f"{data.get('name','')}: {summary} Traits: {', '.join(personality.get('traits', []))}"
        meta = {
            "faction": data.get("faction", ""),
            "role": data.get("role", ""),
            "archetype": data.get("archetype", ""),
            "lore_refs": ",".join(data.get("lore_refs", [])),
            "knowledge_version_id": version_id,
        }
        chunks.append(Chunk(id=f"npc::{npc_id}", domain="npc", text=text, metadata=meta, payload={}))

    # Quests
    for path in content_root.glob("quests/*.json"):
        data = _load_json(path)
        qid = data.get("questId") or path.stem
        stages = data.get("stages", [])
        stage_text = "; ".join(s.get("description", "") for s in stages)
        text = f"{data.get('title','')}: {data.get('description','')} Stages: {stage_text}"
        meta = {
            "giver": data.get("giverId", ""),
            "type": data.get("type", ""),
            "lore_ref": data.get("lore_ref", ""),
            "knowledge_version_id": version_id,
        }
        chunks.append(Chunk(id=f"quest::{qid}", domain="quest", text=text, metadata=meta, payload={}))

    # Scenes
    for path in content_root.glob("scenes/**/*.json"):
        data = _load_json(path)
        scene_id = data.get("sceneId") or path.stem
        segments = data.get("text", {}).get("segments", [])
        text = " ".join(seg.get("md", "") for seg in segments)
        meta = {
            "tags": ",".join(data.get("context", {}).get("tags", [])),
            "lore_refs": ",".join(data.get("context", {}).get("loreRefs", [])),
            "tone": data.get("tone", ""),
            "knowledge_version_id": version_id,
        }
        chunks.append(Chunk(id=f"scene::{scene_id}", domain="scene", text=text, metadata=meta, payload={}))

    # Items/artcards можно добавить при необходимости
    return chunks


def collect_graph_facts(content_root: Path, version_id: str) -> list[dict]:
    facts: list[dict] = []

    # Lore → Concept/Location/Faction
    for path in content_root.glob("lore/**/*.json"):
        data = _load_json(path)
        lid = data.get("id") or path.stem
        kind = path.parts[-2] if len(path.parts) >= 2 else "Concept"
        label = "Concept"
        if "geo" in lid or kind in {"geography", "locations"}:
            label = "Location"
        elif "fac" in lid or kind == "factions":
            label = "Faction"
        body = data.get("body") or {}
        fact = {
            "id": f"lore::{lid}",
            "type": label,
            "knowledge_version_id": version_id,
            "properties": {
                "name": body.get("name") or lid,
                "importance": 5,
                "tags": data.get("tags", []),
            },
            "relations": [],
        }
        facts.append(fact)

    # NPC nodes + member_of faction
    for path in content_root.glob("npc/**/*.json"):
        data = _load_json(path)
        npc_id = data.get("npcId") or path.stem
        faction = data.get("faction")
        relations = []
        if faction:
            relations.append({"to": f"lore::{faction}", "type": "MEMBER_OF", "direction": "out"})
        for ref in data.get("lore_refs", []):
            relations.append({"to": f"lore::{ref}", "type": "ABOUT", "direction": "out"})
        facts.append(
            {
                "id": f"npc::{npc_id}",
                "type": "NPC",
                "knowledge_version_id": version_id,
                "properties": {
                    "name": data.get("name", npc_id),
                    "role": data.get("role", ""),
                    "importance": 5,
                },
                "relations": relations,
            }
        )

    # Quests with giver and lore_ref
    for path in content_root.glob("quests/*.json"):
        data = _load_json(path)
        qid = data.get("questId") or path.stem
        relations = []
        giver = data.get("giverId")
        if giver:
            relations.append({"to": f"npc::{giver}", "type": "INVOLVED_IN", "direction": "out"})
        lore_ref = data.get("lore_ref")
        if lore_ref:
            relations.append({"to": f"lore::{lore_ref}", "type": "INVOLVED_IN", "direction": "out"})
        facts.append(
            {
                "id": f"quest::{qid}",
                "type": "Quest",
                "knowledge_version_id": version_id,
                "properties": {"name": data.get("title", qid), "importance": 7},
                "relations": relations,
            }
        )

    # Scenes as events linked to lore_refs
    for path in content_root.glob("scenes/**/*.json"):
        data = _load_json(path)
        scene_id = data.get("sceneId") or path.stem
        relations = []
        for ref in data.get("context", {}).get("loreRefs", []):
            relations.append({"to": f"lore::{ref}", "type": "APPEARED_IN", "direction": "out"})
        name = data.get("text", {}).get("title") or data.get("sceneId") or path.stem
        facts.append(
            {
                "id": f"scene::{scene_id}",
                "type": "Event",
                "knowledge_version_id": version_id,
                "properties": {"name": name, "importance": 4, "tags": data.get("context", {}).get("tags", [])},
                "relations": relations,
            }
        )

    return facts


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт контента Lore в Memory37/Neo4j")
    parser.add_argument("--content-root", type=Path, default=Path("D:/project/Lore/content"))
    parser.add_argument("--version-id", default="kv_lore_drop1")
    parser.add_argument("--pg-dsn", default=os.environ.get("MEMORY37_DATABASE_URL"))
    parser.add_argument("--neo4j-uri", default=os.environ.get("NEO4J_URI"))
    parser.add_argument("--neo4j-user", default=os.environ.get("NEO4J_USER"))
    parser.add_argument("--neo4j-password", default=os.environ.get("NEO4J_PASSWORD"))
    parser.add_argument("--neo4j-database", default=os.environ.get("NEO4J_DATABASE"))
    parser.add_argument("--use-openai", action="store_true")
    parser.add_argument("--openai-embedding-model", default=os.environ.get("OPENAI_EMBEDDING_MODEL"))
    args = parser.parse_args()

    _load_env_key_if_missing()
    provider = _embedding_provider(args.use_openai or bool(os.environ.get("OPENAI_API_KEY")), args.openai_embedding_model)
    store = _build_store(args.pg_dsn, provider, args.openai_embedding_model)

    # registry/aliases
    registry = KnowledgeVersionRegistry()
    registry.register(KnowledgeVersion(id=args.version_id, semver="1.0.0", kind="lore", status="latest"))
    registry.set_alias("lore_latest", args.version_id)

    chunks = collect_chunks(args.content_root, args.version_id)
    facts = collect_graph_facts(args.content_root, args.version_id)

    # Vector ingest
    async def _upsert_all() -> None:
        domains: dict[str, list[Chunk]] = {}
        for ch in chunks:
            domains.setdefault(ch.domain, []).append(ch)
        for domain, items in domains.items():
            await store.upsert(domain=domain, items=items)  # type: ignore[arg-type]
            print(f"Upserted {len(items)} chunks into domain {domain}")

    asyncio.run(_upsert_all())

    # Graph ingest (optional)
    if GraphClient and args.neo4j_uri:
        cfg = GraphConfig(uri=args.neo4j_uri, user=args.neo4j_user or "", password=args.neo4j_password or "", database=args.neo4j_database)
        client = GraphClient(cfg, registry)
        client.run_default_migrations()
        ingest = GraphIngest(client, registry)
        ingest.ingest_entities(KnowledgeVersionRef(alias="lore_latest"), facts)
        print(f"Ingested {len(facts)} graph facts")
    else:
        print("Neo4j env not configured or memory37_graph not installed; skipped graph ingest")


if __name__ == "__main__":  # pragma: no cover
    main()
