````markdown
----
slug: rpg-bot-memory37-graph-rag-spec
title: "Memory37: GraphRAG-слой на Neo4j и политики версий/TTL индексов"
arch: "rpg-bot"
grade: "senior"
content_type: "spec"
summary: "ТЗ на реализацию графового слоя знаний (GraphRAG на Neo4j) поверх Memory37 + единая система версий и TTL для всех knowledge-индексов."
tags: ["rpg-bot","memory37","graph-rag","neo4j","pgvector","knowledge","ttl","versioning"]
status: "ready-for-codex"
created: "2025-12-02"
updated: "2025-12-02"
version: "1.0.0"
reading_time: "~30 min"
outcomes:
  - "Реализован packages/memory37-graph с устойчивым API для движка и ген-слоёв."
  - "Развёрнут и интегрирован Neo4j-граф (GraphRAG) для лора, квестов и отношений NPC/фракций."
  - "Введена единая модель версий и TTL для всех knowledge-индексов (pgvector + Neo4j + BM25)."
  - "Сценарий stage→smoke→swap alias для безопасного обновления знаний и отката."
----

# 0. Контекст и цели

Memory37 в текущей архитектуре уже описывает:
- разделение доменов знаний (SRD, Lore, Episode, NPC, ArtCards);
- гибридный поиск BM25 + pgvector, RRF, rerank; многоуровневую память; ретрив и сводки; общие принципы версионирования. :contentReference[oaicite:0]{index=0}  

Графовый слой в главе 8 помечен как опциональный GraphRAG (узлы — сущности мира, рёбра — связи/квесты/отношения). :contentReference[oaicite:1]{index=1}  

Задача этого ТЗ — превратить графовый слой и политику версий/TTL в **жёстко определённый, готовый к имплементации компонент**:

1. **GraphRAG на Neo4j**:
   - Явная схема графа (labels, relationship types, свойства, индексы).
   - Инжест данных из существующих источников (content, Lore, Episodic Summaries, NPC-профили).
   - Набор устойчивых запросов GraphRAG, используемых движком/ген-слоями.

2. **Версии + TTL всех индексов знаний**:
   - Единая модель версий/алиасов (stage/latest/archived) для:
     - pgvector-индексов SRD/Lore/Episode/ArtCard;
     - BM25-индексов;
     - Neo4j-графа.
   - Политики TTL/retention для эпизодов, динамических отношений, арт-карт и пр.
   - Операционный сценарий reindex/rollback без потери консистентности.

ТЗ ориентировано на реализацию в монорепозитории: `/packages/memory37`, `/packages/genlayers`, `/contracts`, как зафиксировано в рекомендациях по кодовой базе. :contentReference[oaicite:2]{index=2}  

---

# 1. Область и границы

## 1.1 В scope

1. **Новый пакет** `packages/memory37-graph` (название можно уточнить, но далее считаем таким):
   - Обёртка над Neo4j (driver, модели, миграции, конфиг).
   - Графовая модель домена (узлы/рёбра/свойства).
   - API уровня домена для движка/ген-слоёв (GraphRAG-запросы, инжест, обновления).

2. **Расширение `packages/memory37`**:
   - Модель версий и TTL для векторных/keyword-индексов.
   - Метаданные версий/TTL, согласованные с графом.

3. **Интеграция с существующей Memory37**:
   - Использование Episodic Summary, NPC-профилей, ArtCards как источников для графа. :contentReference[oaicite:3]{index=3}  
   - Согласование ID и неймспейсов.

4. **Операционные сценарии**:
   - Развёртывание Neo4j и базовая схема.
   - Reindex pipeline: stage → smoke → swap alias (latest).
   - TTL-процедуры очистки/архивации.

## 1.2 Out of scope (на сейчас)

- UI/редактор графа для контент-команды (это отдельная фича).
- Визуальный Graph Explorer.
- Сложные алгоритмы community detection / GNN и т.п. — допускаются как extension позже.
- Генерация/обогащение графа напрямую LLM’ом без верификации движком.

---

# 2. Архитектура GraphRAG-слоя

## 2.1 Высокоуровневая схема

Компоненты:

- **Neo4j Cluster** (или single instance на MVP):
  - Хранит граф знаний (узлы/рёбра).
  - Имеет индекс по ID и типам узлов.

- **`packages/memory37-graph`**:
  - `GraphClient` — thin wrapper над Neo4j driver.
  - `GraphSchema` — декларация labels, relationship types, constraints, индексов.
  - `GraphIngest` — пайплайны загрузки:
    - статического лора из content-сервиса;
    - динамики из Episodic Summaries и NPC-профилей. :contentReference[oaicite:4]{index=4}  
  - `GraphRagQueries` — набор готовых запросов для:
    - контекста сцены;
    - NPC-отношений;
    - квест-графа;
    - причинно-следственных цепочек.

- **`packages/memory37`**:
  - Хранит конфигурацию версий и TTL для всех индексов (pgvector/BM25/Neo4j).
  - Предоставляет `KnowledgeVersionRegistry`.

- **`narrative-engine` / `genlayers`**:
  - Используют API `memory37-graph` как ещё один источник контекста (параллельно векторным индексам). :contentReference[oaicite:5]{index=5}  

## 2.2 Поток данных (при генерации сцены)

1. Движок знает `campaign_id`, `party_id`, `scene_id`.
2. Сбор контекста Memory37 (как описано в гл. 8): SRD/Lore/Episodic/NPC/ArtCards. :contentReference[oaicite:6]{index=6}  
3. Дополнительно:
   - `GraphRagQueries.scene_context(scene_id, party_id, knowledge_version)`:
     - находит узлы (локация, активные квесты, NPC) вокруг текущей сцены;
     - достаёт подграф глубины 1–2;
     - сводит рёбра в компактный JSON фактов.
4. Генеративный слой получает:
   - текстовые чанки (RAG);
   - JSON-факты из графа (GraphRAG) → используются для объяснений, связности, NPC-памяти.

---

# 3. Модель данных Neo4j (узлы/рёбра)

## 3.1 Общие принципы

- Используем **labeled property graph** Neo4j:
  - Лейблы: `Location`, `NPC`, `Faction`, `Quest`, `Item`, `Event`, `Concept`, `Episode`, `Party`.
  - Отдельный лейбл `KnowledgeRoot` для версионных якорей.
- Все узлы/рёбра:
  - имеют **глобальный доменный ID**, синхронизированный с content/Memory37 (например, `npc:LiShen`, `loc:graveyard`, `quest:moon_key`). :contentReference[oaicite:7]{index=7}  
  - несут `knowledge_version_id` — внешний ключ на запись в реестре версий.
  - для динамических сущностей (Episode, отношения) — поля TTL/expiry.

## 3.2 Узлы (labels) и их свойства

### 3.2.1 Базовые свойства для всех узлов

```text
Node.common:
  id: string          # доменный ID (уникален в рамках type + knowledge_version)
  type: string        # 'location' | 'npc' | 'faction' | ... (дублирует label для удобства)
  knowledge_version_id: string  # ссылка на версию знаний
  source: string      # 'lore' | 'episode' | 'srd' | 'ugc'
  tags: string[]      # доменные теги
  importance: int     # 0..100, эвристика для приоритета в RAG
  created_at: datetime
  updated_at: datetime
````

### 3.2.2 Location

```text
Label: Location
Props:
  ...Node.common
  region_id: string?      # при наличии
  is_major_hub: boolean
```

### 3.2.3 NPC

```text
Label: NPC
Props:
  ...Node.common
  faction_id: string?
  archetype: string?      # 'warrior','scholar',...
  voice_tts: string?      # для TTS-профиля
  alignment: string?      # если используется
```

(синхронизация с NPC-профилем Memory37: `npc_id`, `voice_tts`, `dynamic.disposition` и пр. )

### 3.2.4 Faction, Quest, Item, Event, Concept, Episode, Party

Аналогично: минимальный доменный набор + общие свойства:

* **Faction**: `kind`, `reputation_scale`, `homeland_location_id`.
* **Quest**: `status_schema_version`, `difficulty`, `is_main`.
* **Item**: `rarity`, `is_artifact`, `soulbound`.
* **Event**: точка истории/аномалия (связана с Episode).
* **Concept**: абстрактные сущности (религии, идеи, законы).
* **Episode**: ссылка на `summary_id` из Episodic Summary; краткая типизация (`"bargain"`, `"combat"`, …).
* **Party**: `party_id`, `campaign_id`.

## 3.3 Типы связей (relationship types)

Набор базовых типов (минимум, можно расширять):

```text
RELATIONSHIP    # NPC <-> NPC / NPC <-> Faction (allied_with/enemy_of/neutral)
MEMBER_OF       # NPC -> Faction
LOCATED_IN      # NPC/Quest/Event/Item -> Location
OWNS            # Party/NPC/Faction -> Item
INVOLVED_IN     # NPC/Party/Faction/Location -> Quest/Event
BLOCKS          # Quest/Location/Item -> Quest/Event (гейт)
UNLOCKS         # Item/Event -> Quest/Location
CAUSES          # Event -> Event/State
NEXT_EPISODE    # Episode -> Episode (хронология кампании)
APPEARED_IN     # NPC/Item/Faction -> Episode
ABOUT           # Concept -> NPC/Location/Quest/…
HAS_TAG         # Node -> Concept (как онтологический tag)
```

Свойства рёбер:

```text
Rel.common:
  type: string              # дублирует relationship type
  knowledge_version_id: string
  source: string            # 'authoring' | 'episode' | 'inferred'
  weight: float             # -1..+1 для отношений/важности связи
  confidence: float         # 0.0..1.0 для inferred-связей
  since: datetime
  until: datetime?          # можно использовать для TTL или версионности
  expires_at: datetime?     # для динамических связей
```

## 3.4 Индексы и ограничения Neo4j

Обязательные:

* Уникальный индекс на `(label, id, knowledge_version_id)`.
* Индексы по `knowledge_version_id` для быстрого фильтра.
* FULLTEXT-индекс (опционально) по `tags` и лёгким текстовым полям (если будут).

Ограничения:

* Нельзя создать `RELATIONSHIP` между узлами с разными `knowledge_version_id` (проверка на уровне кода, возможно constraint через APOC-процедуры).

---

# 4. Версионность знаний и TTL (единая модель)

## 4.1 Реестр версий знаний

В `packages/memory37` вводим сущность:

```text
KnowledgeVersion:
  id: string           # 'kv_2025_12_01_r1'
  semver: string       # '1.3.0'
  kind: string         # 'srd' | 'lore' | 'episode' | 'global'
  status: string       # 'stage' | 'latest' | 'archived'
  created_at: datetime
  activated_at: datetime?  # момент, когда стала latest
  notes: string?
```

Плюс алиасы:

```text
KnowledgeAlias:
  name: string         # 'lore_latest', 'lore_stage', 'episode_latest'
  version_id: string   # FK на KnowledgeVersion.id
```

Все индексы (pgvector/BM25/Neo4j) привязываются к `KnowledgeVersion.id` (или группе версий, если нужно разделение по доменам).

## 4.2 Версии pgvector/BM25

Для каждого домена (srd/lore/episode/art) в существующей схеме Memory37:

* добавляем поле `knowledge_version_id` в таблицы embeddings/keywords;
* включаем его в ключи/индексы;
* все запросы ретрива фильтруют по `knowledge_version_id`:

```sql
WHERE knowledge_version_id = :current_version_id
```

Версионирование данных лора уже описано: SemVer на уровне чанка + алиасы latest/stage. 
Здесь мы фиксируем **операционный слой**:

* смена версии = смена алиаса `lore_latest`/`episode_latest` на другой `KnowledgeVersion.id`;
* в коде `memory37` используется только алиас, а не конкретный id.

## 4.3 Версии Neo4j-графа

Для Neo4j:

* Вводится **корневой узел** `(:KnowledgeRoot { version_id, kind })`.
* Все узлы/рёбра данного снапшота имеют `knowledge_version_id = version_id`.
* Для `kind='lore'` и `kind='episode'` возможны разные версии (например, lore обновился, а эпизоды остаются).

Смена версии:

1. Встроенные конфиги `KnowledgeAlias` обновляются (например, `lore_stage` → `kv_2025_12_01_r1`).
2. Скрипты/сервисы, работающие с Neo4j, используют **текущий alias**:

   * при чтении: `MATCH (n) WHERE n.knowledge_version_id = $version_id …`
   * при записи: `SET n.knowledge_version_id = $version_id`.
3. Для переключения `stage→latest` достаточно поменять alias.

## 4.4 TTL и retention

### 4.4.1 Домены и сроки

На базе политики из гл. 8 и 5:  

* **SRD/Rules**:

  * TTL не применяется (нормативные данные).
  * Изменения только через новую версию.

* **Lore**:

  * TTL не применяется, но возможно перевод версии в `archived`.
  * Жёсткий контроль ревизий и свопа алиасов.

* **Episode/Episodic Summaries**:

  * TTL 90–180 дней после завершения кампании (по конфигу).
  * В pgvector/BM25/Neo4j — поля `expires_at` и фоновые джобы очистки/архивации.

* **NPC динамика (отношения)**:

  * TTL после окончания кампании (например, `180d`) с опцией «заморозить» как canonical-историю (архив).

* **ArtCards**:

  * TTL по медиа-политике: 30 дней CDN + долгая архивная зона (см. гл. 5). 

### 4.4.2 Реализация TTL

* В PostgreSQL:

  * периодический джоб (`cron`) удаляет/архивирует записи, где `expires_at < now()`.
  * отдельные таблицы для архивов, либо soft-delete флаг `is_archived`.

* В Neo4j:

  * либо APOC-процедуры (планировщик), либо внешний скрипт:

    * `MATCH (n) WHERE n.expires_at < datetime() DETACH DELETE n`.
  * для некоторых доменов вместо DELETE — перенос в `archived`-граф (опционально).

* Условия:

  * удаления согласованы: сначала эпизоды/отношения в Neo4j, затем соответствующие в pgvector/BM25.

---

# 5. Инжест и обновление графа

## 5.1 Источники данных

1. **Статический лор**:

   * JSON из `content/lore/*.json` (описания локаций, фракций, персонажей). 
2. **NPC-профили**:

   * JSON-профили NPC (static + dynamic), включая disposition/relations. 
3. **Episodic Summaries**:

   * JSON-сводки ходов/сцен (кто, где, что произошло, дельты отношений, флаги квестов). 
4. **ArtCards** (опционально):

   * для визуальных связей (NPC/Location/Item ↔ визуальные теги/стили).

## 5.2 Пайплайн `GraphIngest` (offline/батч)

Для каждой новой `KnowledgeVersion`:

1. **Инициализация**:

   * создаётся `KnowledgeRoot` узел.
   * в Postgres создаётся запись `KnowledgeVersion`.
2. **Инжест лора**:

   * чтение `content/lore` → маппинг в узлы `Location`, `Faction`, `Concept`, `NPC` (статическая часть).
   * установка рёбер `LOCATED_IN`, `MEMBER_OF`, `RELATIONSHIP` (alliances/enemies).
3. **Инжест NPC-профилей**:

   * обновление/создание узлов `NPC` (dynamic часть).
   * создание/обновление связей `RELATIONSHIP` (по disposition), `MEMBER_OF`.
4. **Инжест Episodic Summaries**:

   * узлы `Episode` (по `summary_id`).
   * `APPEARED_IN` между Episode и NPC/Item/Faction.
   * `INVOLVED_IN` между Episode и Quest/Location.
   * `NEXT_EPISODE` между эпизодами кампании.
   * `CAUSES`, `BLOCKS`, `UNLOCKS` (если закодированы в флагах).
5. **Инжест ArtCards**:

   * связи `ABOUT`/`HAS_TAG` между Concept/Location/NPC и визуальными концептами.

Должен быть **идемпотентный** по (version_id, source) и устойчивый к повторным прогоном (upsert-логика).

## 5.3 Online-обновления (во время кампании)

Для **текущих** кампаний:

* события типа:

  * изменение отношения NPC к партии;
  * завершение квеста;
  * критический сюжетный поворот;
* должны приводить к обновлению графа:

```text
GraphIngest.apply_episode_delta(episodic_summary)
```

* обновляет:

  * свойства узлов (например, disposition).
  * создаёт/обновляет связи `RELATIONSHIP`, `INVOLVED_IN`, `CAUSES`, `BLOCKS`, `UNLOCKS`.
* все такие записи маркируются `source='episode'` и получают `expires_at` согласно TTL.

---

# 6. API `packages/memory37-graph`

## 6.1 Базовые интерфейсы (псевдо-TS)

```ts
// Конфиг версии и подключения
interface GraphConfig {
  uri: string
  user: string
  password: string
  database: string
}

interface KnowledgeVersionRef {
  alias: string        // 'lore_latest' | 'episode_latest' | ...
  versionId?: string   // опционально прямой id (перекрывает alias)
}
```

### 6.1.1 GraphClient

```ts
class GraphClient {
  constructor(config: GraphConfig, versionRegistry: KnowledgeVersionRegistry)

  getSession(version: KnowledgeVersionRef): Neo4jSession
  withVersion<T>(version: KnowledgeVersionRef, fn: (session) => Promise<T>): Promise<T>
}
```

### 6.1.2 GraphRagQueries

Минимальный набор:

```ts
interface SceneGraphContextRequest {
  sceneId: string
  campaignId: string
  partyId: string
  version: KnowledgeVersionRef
  maxDepth?: 1 | 2
  maxNodes?: number    // дефолт ~100
}

interface SceneGraphContext {
  nodes: GraphNodeFact[]
  relations: GraphRelationFact[]
  summary: string      // краткая сводка подграфа (≤ 300 символов)
}

interface GraphNodeFact {
  id: string
  type: string
  tags: string[]
  importance: number
  meta: Record<string, any> // e.g. {"faction_id":"...", "location_id":"..."}
}

interface GraphRelationFact {
  from: string
  to: string
  type: string
  weight: number
  source: string
}
```

Методы:

```ts
class GraphRagQueries {
  constructor(graphClient: GraphClient)

  sceneContext(req: SceneGraphContextRequest): Promise<SceneGraphContext>

  npcSocialContext(npcId: string, partyId: string, version: KnowledgeVersionRef): Promise<SceneGraphContext>

  questGraphContext(questId: string, version: KnowledgeVersionRef): Promise<SceneGraphContext>

  causalChain(
    fromEventId: string,
    toEventId?: string,
    version: KnowledgeVersionRef,
    maxHops?: number
  ): Promise<SceneGraphContext>
}
```

### 6.1.3 Ingest API

```ts
class GraphIngest {
  constructor(graphClient: GraphClient)

  ingestLore(versionId: string, loreChunks: LoreChunk[]): Promise<void>
  ingestNpcProfiles(versionId: string, npcProfiles: NpcProfile[]): Promise<void>
  ingestEpisodes(versionId: string, episodes: EpisodicSummary[]): Promise<void>

  applyEpisodeDelta(summary: EpisodicSummary): Promise<void>  // online-обновления
}
```

Типы `LoreChunk`, `NpcProfile`, `EpisodicSummary` должны быть синхронизированы с JSON-схемами Memory37 (гл. 8). 

## 6.2 Требования к API

* **Стабильность**: публичные интерфейсы не ломаем; breaking → новая мажорная версия пакета.
* **Идемпотентность**: многократный вызов `ingest*` c одинаковыми данными не приводит к дублированию узлов/рёбер.
* **Наблюдаемость**:

  * все публичные методы эмитят OpenTelemetry-спаны `memory37.graph.*` с атрибутами:

    * `knowledge.version_id`, `knowledge.alias`, `graph.nodes_count`, `graph.relations_count`, `graph.depth`, `graph.query_type`. 

---

# 7. Запросы GraphRAG: стратегии

## 7.1 Scene Context

Алгоритм `sceneContext` (в общих шагах):

1. Определить связанные сущности:

   * по `scene_id` → список `location_id`, `quest_id`, `npc_ids`, `party_id` (берётся из БД контента/эпизодов).
2. В графе:

   * найти узлы этих сущностей (match по id + version_id).
   * выполнить расширение `maxDepth` по рёбрам типов:

     * `LOCATED_IN`, `MEMBER_OF`, `RELATIONSHIP`, `INVOLVED_IN`, `BLOCKS`, `UNLOCKS`, `OWNS`.
3. Ограничить подграф:

   * по `importance` (отсечь малозначимые узлы);
   * по `maxNodes`.
4. Подготовить `SceneGraphContext`:

   * список узлов и рёбер;
   * вычислить краткую текстовую сводку подграфа (через лёгкий LLM-вызов или шаблон).

## 7.2 NPC Social Context

Цель — дать движку/ген-слою компактную картину **отношений NPC ↔ пати и мир**:

* исходные узлы: `NPC`, `Party`, связанные `Faction`, `Location`, `Episode` (последние по времени);
* расширение по `RELATIONSHIP`, `MEMBER_OF`, `APPEARED_IN`, `INVOLVED_IN`.

Выход:

* список фактов: «NPC состоит во фракции X, у фракции конфликт с фракцией Y, пати имеет репутацию Z у X, последняя значимая сцена N…» (структурировано в JSON, не плейнтекст).

## 7.3 Quest Graph Context

Цель — показать структуру квеста:

* узел `Quest` + все связанные `Location`, `NPC`, `Event`, `Item`;
* входящие/исходящие `BLOCKS`, `UNLOCKS`, `CAUSES`;
* цепочки `NEXT_EPISODE` и появление пати в эпизодах.

Используется:

* для объяснений игроку «что ещё осталось сделать»;
* для планирования генеративных сцен (какие ветки ещё не тронуты).

## 7.4 Causal Chain

Для вопросов типа «как мы оказались в этой ситуации»:

* от Event/Aggregated Episode до текущего Event/Episode;
* поиск путей через `CAUSES`, `BLOCKS`, `UNLOCKS`, `INVOLVED_IN`.

Ограничения:

* `maxHops` 3–4 для MVP;
* хранить только наиболее «тяжёлые» по weight рёбра.

---

# 8. Операции, миграции, observability

## 8.1 Развёртывание Neo4j

Минимум:

* docker-compose или helm-чарт для Neo4j:

  * persistence включен;
  * конфиги безопасности (пароль, TLS при необходимости).
* отдельный `database` (если поддерживается) для RPG-Bot.

## 8.2 Миграции схемы графа

Реализовать простой слой миграций:

* каталог `/packages/memory37-graph/migrations`:

  * скрипты с версионированием (`001_init.cql`, `002_add_indexes.cql`, …).
* утилита `graph:migrate`:

  * применяет миграции по порядку;
  * пишет текущую версию в `KnowledgeRoot` (или отдельный сервисный узел/таблицу в Postgres).

## 8.3 Мониторинг и алёрты

Метрики:

* latency p50/p95 запросов `sceneContext`, `npcSocialContext`, `questGraphContext`;
* количество узлов/рёбер по `knowledge_version_id`;
* ошибки/тайм-ауты драйвера.

Алерты:

* повышенный error-rate на `memory37.graph.*`;
* существенный рост размера графа (аномалия).

Все метрики интегрируются в общую observability-модель (OTel, SLO). 

## 8.4 Деградации

При недоступности Neo4j:

* `memory37-graph` должен:

  * логировать ошибку;
  * возвращать `SceneGraphContext` с пустыми списками и флагом `degraded: true`.
* Движок/ген-слой:

  * продолжают работу только на vektor/BM25 Memory37.

---

# 9. План задач для Codex (WBS)

Ниже — конкретные задачи под Codex/команду разработки.

## 9.1 Подготовительные

1. **TASK-1: Структура пакета**

   * Создать `packages/memory37-graph` с каркасом:

     * `src/client.ts`, `src/schema.ts`, `src/ingest.ts`, `src/queries.ts`, `src/index.ts`.
   * Настроить зависимости (Neo4j driver, OTel-хуки).

2. **TASK-2: KnowledgeVersionRegistry**

   * В `packages/memory37` реализовать реестр версий/алиасов:

     * модели `KnowledgeVersion`, `KnowledgeAlias`;
     * методы `getVersionId(alias)`, `setAlias(alias, versionId)`.

## 9.2 Графовая модель и миграции

3. **TASK-3: GraphSchema & миграции**

   * Описать labels/relationship types/свойства по этому ТЗ.
   * Реализовать миграции (создание индексов, constraints).
   * Скрипт `graph:migrate`.

4. **TASK-4: GraphClient**

   * Реализовать обёртку над Neo4j-сессиями с поддержкой `KnowledgeVersionRef` и OTel-трассировкой.

## 9.3 Инжест

5. **TASK-5: Lore ingest**

   * Функции `ingestLore(versionId, loreChunks)`.
   * Маппинг из существующих лор-структур в узлы/рёбра.

6. **TASK-6: NPC ingest**

   * `ingestNpcProfiles(versionId, npcProfiles)`.
   * Создание/обновление NPC и связей `MEMBER_OF`, `RELATIONSHIP`.

7. **TASK-7: Episodic ingest & applyEpisodeDelta**

   * `ingestEpisodes(versionId, episodes)` и `applyEpisodeDelta(summary)`.
   * Создание узлов Episode и рёбер `APPEARED_IN`, `INVOLVED_IN`, `NEXT_EPISODE`, `CAUSES`, `BLOCKS`, `UNLOCKS`.

## 9.4 GraphRAG-запросы

8. **TASK-8: SceneGraphContext**

   * Реализовать `sceneContext(req)` с описанной выше логикой.
   * Добавить unit/integration-тесты на небольшой фикстуре графа.

9. **TASK-9: NPC Social & Quest Context**

   * Реализовать `npcSocialContext`, `questGraphContext`.
   * Обеспечить ограничение размера подграфа и сжатие в JSON-факты.

10. **TASK-10: CausalChain**

    * Реализовать `causalChain` (поиск путей).
    * Предусмотреть тайм-аут и ограничение по hops/узлам.

## 9.5 Версионирование и TTL

11. **TASK-11: Версионные фильтры**

    * Обновить векторный/keyword-ретрив в `memory37` для использования `KnowledgeVersionRef`.
    * Добавить конфиги alias’ов (`lore_latest`, `lore_stage`, `episode_latest`).

12. **TASK-12: TTL-политики и джобы**

    * Реализовать фоновые процессы удаления/архивации:

      * в Postgres (эпизоды, динамика NPC).
      * в Neo4j (узлы/рёбра с `expires_at`).
    * Проверка согласованности удаления.

## 9.6 Observability & деградации

13. **TASK-13: OTel-интеграция**

    * Спаны `memory37.graph.*`, атрибуты, метрики.
    * Базовые алёрты (описать в ops-конфиге).

14. **TASK-14: Fallback-логика**

    * Защитная обёртка вокруг всех публичных методов GraphRAG:

      * в случае ошибок Neo4j — graceful fallback и лог.

---

# 10. Критерии готовности (DoD)

Функциональные:

* `packages/memory37-graph` подключается к Neo4j и успешно:

  * прогоняет миграции;
  * загружает лор/NPC/эпизоды;
  * отдаёт осмысленные `SceneGraphContext` по тестовому модулю.

* Версии знаний:

  * alias `lore_latest` / `lore_stage` / `episode_latest` работают;
  * переключение alias’ов отражается во всех ретривах (pgvector/BM25/Neo4j) без релиза кода.

* TTL:

  * по истечении TTL эпизоды и динамические отношения исчезают из индексов и графа;
  * статический лор не затрагивается.

Нефункциональные:

* p95 latency запросов `sceneContext`/`npcSocialContext` ≤ заданного порога (например, ≤ 50–80 мс для средних графов) — фиксируется в метриках.
* Ошибки Neo4j не ломают основной игровой флоу: GraphRAG может быть отключён без падения движка.
* Есть минимальный набор unit/integration-тестов на `GraphIngest` и `GraphRagQueries`.


```
```
