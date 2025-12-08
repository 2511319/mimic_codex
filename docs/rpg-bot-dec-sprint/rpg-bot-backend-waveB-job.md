----
slug: rpg-bot-backend-waveB
title: "RPG-Bot Backend Wave B: Memory37 core + GraphRAG + версии/TTL"
wave: "B"
priority: "P0"
branch: "feat/rpg-backend-waveB"
repo_root: "D:\\project\\mimic_codex"
specs:
  - "docs/rpg-bot-backend-execution-plan-v1.md"
  - "docs/rpg-bot-memory37-core-spec.md"
  - "docs/rpg-bot-memory37-graph-rag-spec.md"
services:
  - "packages/memory37"
  - "packages/memory37-graph"
  - "services/gateway_api"
status: "ready-for-codex"
outcomes:
  - "Реализован Memory37 core (pgvector + ingest + API чтения) и интегрирован в gateway."
  - "Реализован Memory37-graph (Neo4j GraphRAG) с версиями знаний и TTL-политиками."
  - "Версионирование/TTL согласовано между pgvector/BM25 и Neo4j, alias’ы latest/stage работают."
----

## Цель Wave B

Сделать полноценный слой знаний Memory37:

- Core: SRD/Lore/Episode/NPC/Art в pgvector/BM25, ingestion и API.
- GraphRAG: Neo4j-граф поверх тех же данных.
- Версии и TTL: единая модель версий знаний для всех индексов.

Wave B выполняется **после** завершения Wave A. Никакой работы по Genlayers и `/v1/generate/*` в этой волне не делать.

---

## Контекст и документация

Прочитать:

1. `docs/rpg-bot-backend-execution-plan-v1.md` — разделы Wave B.
2. `docs/rpg-bot-memory37-core-spec.md` — ТЗ на Memory37 core и интеграцию в gateway.
3. `docs/rpg-bot-memory37-graph-rag-spec.md` — ТЗ на GraphRAG-слой и версии/TTL.

---

## Область работ

### 1. Memory37 core (packages/memory37 + gateway_api/knowledge)

**Пакет `packages/memory37`:**

- Реализовать структуру, описанную в ТЗ:
  - `config.py` — конфиги доменов (`srd`, `lore`, `episode`, `npc`, `art`), embedding-параметры, режимы поиска.
  - `types.py` — Pydantic-модели:
    - `EpisodicSummary`,
    - `NPCProfile`,
    - `ArtCard`,
    - `Chunk`, `GraphFact` (если используется в core).
  - `stores/base.py` — протоколы `VectorStore`, `GraphStore` (GraphStore можно сделать заглушкой и отдать реализацию в memory37-graph).
  - `stores/pgvector_store.py` — реализация `VectorStore` на PostgreSQL+pgvector.
  - `ingest/normalizer.py`, `chunker.py`, `embedder.py`, `indexer.py`:
    - пайплайн normalize → chunk → embed → upsert для SRD/Lore/Episode/Art.

- Реализовать high-level API (модули `api/*.py`):
  - `lore.py`: `lore_search`.
  - `rules.py`: `rules_lookup`.
  - `episode.py`: `session_fetch`.
  - `npc.py`: `npc_profile`.
  - `art.py`: `art_suggest`.
  - `assert_.py`: `lore_assert`.

**Интеграция с gateway:**

- В `services/gateway_api`:
  - модуль `knowledge.py` с `KnowledgeService` как thin-wrapper над Memory37:
    - инициализация сторей и embedding по настройкам;
    - `search`/`lore_search`/`rules_lookup` и т.п.
  - endpoint `/v1/knowledge/search`:
    - принимает текстовый запрос;
    - возвращает массив knowledge-элементов (структура из ТЗ).

**Тесты и проверки:**

- Smoke-тест ingestion:
  - загрузка небольшого тестового набора SRD/Lore/Episode в локальную БД.
- Проверка `lore_search` и `rules_lookup`:
  - запрос по заведомо существующим терминам → не пустой результат.
- Проверка `/v1/knowledge/search` в dev-окружении.

---

### 2. Memory37 GraphRAG + версии/TTL (packages/memory37-graph + Neo4j)

**Пакет `packages/memory37-graph`:**

- Реализовать:

  1. `GraphClient`:
     - подключение к Neo4j (URI, user, password, database);
     - интеграция с `KnowledgeVersionRegistry` (берёт versionId/alias).

  2. `GraphSchema` и миграции:
     - labels: `Location`, `NPC`, `Faction`, `Quest`, `Item`, `Event`, `Concept`, `Episode`, `Party`, `KnowledgeRoot`;
     - relationships: `RELATIONSHIP`, `MEMBER_OF`, `LOCATED_IN`, `OWNS`, `INVOLVED_IN`, `BLOCKS`, `UNLOCKS`, `CAUSES`, `NEXT_EPISODE`, `APPEARED_IN`, `ABOUT`, `HAS_TAG`;
     - индексы/constraints (уникальность `(label, id, knowledge_version_id)`).

  3. `GraphIngest`:
     - `ingestLore(versionId, loreChunks)`;
     - `ingestNpcProfiles(versionId, npcProfiles)`;
     - `ingestEpisodes(versionId, episodes)`;
     - `applyEpisodeDelta(summary)` для онлайн-обновлений.

  4. `GraphRagQueries`:
     - `sceneContext(req)`;
     - `npcSocialContext(npcId, partyId, versionRef)`;
     - `questGraphContext(questId, versionRef)`;
     - `causalChain(fromEventId, toEventId?, versionRef, maxHops?)`.

**Версии и TTL:**

- В core (`packages/memory37`):

  - `KnowledgeVersion` и `KnowledgeAlias` (registry);
  - все таблицы pgvector/BM25 снабжены `knowledge_version_id`;
  - все запросы индексов фильтруют по версии (через alias типа `lore_latest`).

- В Neo4j:

  - узлы/рёбра содержат `knowledge_version_id`;
  - есть `KnowledgeRoot` для каждой версии;
  - переключение alias’ов (`lore_latest`, `lore_stage`, `episode_latest`) меняет версию без изменения кода.

- TTL-политики:

  - для episodic данных и динамических отношений (NPC relations, Episode):
    - поля `expires_at`/`until`;
    - фоновый процесс очистки и/или архивации в pgvector/BM25 и Neo4j.

**Тесты и проверки:**

- Миграции:
  - `graph:migrate` отрабатывает без ошибок на чистой БД.

- Ingest:
  - на тестовом наборе:
    - в Neo4j создаются ожидаемые узлы/рёбра;
    - запрос `sceneContext` возвращает компактный подграф.

- Версии:
  - создать две версии лора;
  - убедиться, что при смене alias’а `lore_latest` ответы меняются без изменения кода.

---

## Границы ответственности Wave B

- Не внедрять Genlayers и `/v1/generate/*` — это Wave C.
- Не менять API Party Sync, Media-broker и их логику, кроме случаев, если Memory37 требует минимальной интеграции (обычно не требуется).

---

## Definition of Done (Wave B)

Wave B завершена, если:

1. Memory37 core:
   - реализованы ingestion-пайплайны и API `lore_search`, `rules_lookup`, `session_fetch`, `npc_profile`, `art_suggest`, `lore_assert`;
   - `KnowledgeService` в gateway работает;
   - `/v1/knowledge/search` отдаёт корректный результат.

2. Memory37-graph:
   - Neo4j-схема развёрнута и миграции проходят;
   - `sceneContext`/`npcSocialContext`/`questGraphContext`/`causalChain` возвращают осмысленные графовые факты;
   - версии/alias’ы работают, TTL-политики заведены.

3. Документация:
   - краткое описание того, какие версии/alias’ы заведены;
   - пример запроса/ответа `sceneContext` на тестовой сцене.

В отчёте указать:

- какие файлы в `packages/memory37` и `packages/memory37-graph` изменены/созданы;
- какие команды миграций и тестов запускались;
- подтверждение по пунктам DoD.
