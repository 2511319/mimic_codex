# Memory37 GraphRAG (Neo4j)

Каркас графового слоя для Memory37. Поддерживает два режима:

1) **Neo4j** — при наличии драйвера и настроек (`GraphConfig`).
2) **In-memory fallback** — если Neo4j недоступен (для локальной разработки и тестов).

## Конфигурация Neo4j

```python
from memory37_graph import GraphClient, GraphConfig, GraphIngest, GraphRagQueries, KnowledgeVersionRef
from memory37 import KnowledgeVersionRegistry, KnowledgeVersion

registry = KnowledgeVersionRegistry()
registry.register(KnowledgeVersion(id="kv_2025_12", semver="1.0.0", kind="lore", status="latest"))

config = GraphConfig(
    uri="bolt://localhost:7687",
    user="neo4j",
    password="password",
    database=None,  # опционально
)
client = GraphClient(config=config, version_registry=registry)
client.run_default_migrations()
ingest = GraphIngest(graph_client=client, version_registry=registry)
queries = GraphRagQueries(graph_client=client, ingest=ingest)
```

## Инжест (пример)

```python
from memory37.domain import KnowledgeItem, NpcProfile

lore_chunks = [
    KnowledgeItem(item_id="lore::tower", domain="lore", content="Ancient tower", metadata={"tags": "ruins"}),
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

# Универсальный ingest для Location/Faction/Quest/Event/Item
facts = [
    {
        "id": "loc::forest",
        "type": "Location",
        "properties": {"tags": ["nature"], "importance": 5},
        "relations": [{"to": "faction::wardens", "type": "MEMBER_OF", "direction": "out"}],
    },
    {
        "id": "quest::moon",
        "type": "Quest",
        "properties": {"difficulty": "medium", "importance": 10},
        "relations": [{"to": "loc::forest", "type": "INVOLVED_IN", "direction": "out"}],
    },
]
ingest.ingest_entities(KnowledgeVersionRef(alias="lore_latest"), facts)
```

## Запросы GraphRAG (пример)

```python
ctx = queries.scene_context(
    SceneGraphContextRequest(
        scene_id="scn_1",
        campaign_id="cmp_1",
        party_id="pty_1",
        version=KnowledgeVersionRef(alias="lore_latest"),
        max_depth=1,
        max_nodes=100,
    )
)
print(ctx.summary, ctx.degraded)
```

## TTL и очистка

- Узлы/рёбра могут содержать `expires_at` (ISO datetime). `GraphIngest` выставляет TTL по умолчанию для эпизодов/отношений (180 дней) и квестовых/каузальных рёбер (365 дней), `cleanup_expired()` удаляет просроченное в памяти и Neo4j.
- Для прод-использования добавьте планировщик (cron/APOC) и доменные политики (эпизоды, отношения NPC/фракций). Пример APOC:

```
CALL apoc.periodic.repeat(
  'cleanup_nodes',
  'MATCH (n) WHERE n.expires_at IS NOT NULL AND datetime(n.expires_at) < datetime() DETACH DELETE n',
  3600
);
CALL apoc.periodic.repeat(
  'cleanup_rels',
  'MATCH ()-[r]-() WHERE r.expires_at IS NOT NULL AND datetime(r.expires_at) < datetime() DELETE r',
  3600
);
```

## Smoke-команды

- In-memory тест: `PYTHONPATH=packages/memory37-graph/src; python -m pytest packages/memory37-graph/tests/test_graph_inmemory.py -q`
- При наличии Neo4j: настройте `GraphConfig`, вызовите `run_default_migrations()`, затем `ingest_*` и `queries.scene_context(...)`.

## Деградация

- Если Neo4j недоступен, GraphClient автоматически падает в in-memory режим; `SceneGraphContext.degraded=True` сигнализирует об использовании fallback.

## Docker Compose (Neo4j пример)

```yaml
services:
  neo4j:
    image: neo4j:5.25
    container_name: neo4j
    environment:
      - NEO4J_AUTH=neo4j/password
    ports:
      - "7474:7474"
      - "7687:7687"
    volumes:
      - neo4j_data:/data
volumes:
  neo4j_data: {}
```

Переменные для подключения из кода:
- `NEO4J_URI=bolt://localhost:7687`
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=password`

Aliасы версий:
- `KnowledgeVersionRef(alias="lore_latest")` или `version_id="kv_..."`.

## E2E smoke с Neo4j

1. Поднимите Neo4j (docker-compose выше), создайте `.env`:
   ```
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=password
   ```
2. В интерактивном python:
   ```python
   from memory37_graph import GraphClient, GraphConfig, GraphIngest, GraphRagQueries, KnowledgeVersionRef
   from memory37 import KnowledgeVersionRegistry, KnowledgeVersion
   registry = KnowledgeVersionRegistry()
   registry.register(KnowledgeVersion(id="kv_smoke", semver="1.0.0", kind="lore", status="latest"))
   cfg = GraphConfig(uri="bolt://localhost:7687", user="neo4j", password="password")
   client = GraphClient(cfg, registry); client.run_default_migrations()
   ingest = GraphIngest(client, registry)
   ingest.ingest_entities(KnowledgeVersionRef(alias="lore_latest"), [
       {"id": "loc::forest", "type": "Location", "properties": {"importance": 5}, "relations": []},
       {"id": "quest::moon", "type": "Quest", "properties": {"importance": 10},
        "relations": [{"to": "loc::forest", "type": "INVOLVED_IN", "direction": "out"}]},
   ])
   queries = GraphRagQueries(client, ingest)
   ctx = queries.scene_context(SceneGraphContextRequest(scene_id="quest::moon", campaign_id="*", party_id="*", version=KnowledgeVersionRef(alias="lore_latest")))
   print(ctx.summary)
   ```
3. Gateway: задайте `NEO4J_URI/USER/PASSWORD` и вызовите `/v1/graph/scene?scene_id=quest::moon` — ожидается JSON с nodes/relations, `degraded=false`.
