# Memory37 — ТЗ для Codex

`packages/memory37` + интеграция в `gateway`

---

## 0. Контекст и принятые решения

**Роль Memory37.** Это отдельный слой знаний и памяти ИИ-ведущего: SRD/правила, лор, эпизодические сводки кампаний, профили NPC и визуальные ArtCards. Он обеспечивает гибридный поиск (BM25 + вектор) и, опционально, графовые запросы поверх знаний мира.

**Принятые технологии:**

* **Реляционное/векторное хранилище:** PostgreSQL + `pgvector` (основной стор для SRD/Lore/Episode/ArtCards).
* **Графовое хранилище:** **Neo4j** как реализация опционального GraphRAG-слоя (персонажи, локации, квест-объекты, связи).

**Уровни памяти, которые должен поддерживать код:**

* рабочая (на один запрос / сцену),
* краткосрочная (thread/step-state),
* долгосрочная (персистентные сводки, отношения NPC, ArtCards).

**Ограничения по этапу:**

* Фокус — **рабочий функционал** Memory37 и его интеграция с gateway и LLM-tools.
* Юнит-тесты — **минимальный уровень**: smoke-тесты ключевых функций (`ingest`, `search`, `npc_profile` и т.п.), без попытки полного покрытия.

---

## 1. Общая архитектура Memory37

Опираться на главу 8 «Память37» как на функциональную спецификацию.

### 1.1 Домены знаний

Memory37 должен различать следующие домены:

* `srd` — правила/SRD (норматив механик, термины, глоссарий).
* `lore` — лор, локации, фракции, биографии, таймлайны.
* `episode` — **Episodic Summaries** (сводки сцен/ходов кампаний).
* `npc` — динамические профили NPC (отношения, память о событиях).
* `art` — ArtCards (словесные описания арта, теги, стиль, seed).

### 1.2 Физические хранилища

1. **Postgres + pgvector:**

   * таблицы для `srd`, `lore`, `episode`, `art`; каждая содержит:

     * `id` (ULID/UUIDv7),
     * `text`/`payload` (JSONB),
     * `embedding` (`vector`),
     * `metadata` (JSONB с доменными полями),
     * служебные поля `created_at`, `updated_at`, `version`.

2. **Граф (Neo4j):**

   * узлы: `Character`, `Location`, `Item`, `Faction`, `Quest`, `Event`;
   * рёбра: `KNOWS`, `LOCATED_IN`, `OWNS`, `ALLY_WITH`, `ENEMY_OF`, `PART_OF`, `RELATES_TO` и т.п.;
   * хранит только устойчивые факты/отношения (не «каждое действие»).

3. **Keyword/BM25 слой:**

   * либо Postgres full-text (`tsvector`), либо выделенный search-стор (этап 1: **pg FTS**).
   * используется совместно с векторным поиском и RRF-фьюжном.

### 1.3 Паттерн использования

* **Запись в память** — только движком/редактором (backend), Memory37 не пишет самовольно от лица LLM.
* **Чтение** — через строго типизированные функции `memory37` и LLM-tools (см. §5 и §7).

---

## 2. Структура пакета `packages/memory37`

Создать пакет:

```text
/packages/memory37
  /memory37
    __init__.py
    config.py
    types.py
    stores/
      base.py
      pgvector_store.py
      neo4j_graph.py
    ingest/
      normalizer.py
      chunker.py
      embedder.py
      indexer.py
    api/
      lore.py
      rules.py
      episode.py
      npc.py
      art.py
      assert_.py
    observability.py
  pyproject.toml
  README.md
```

### 2.1 Базовые интерфейсы (`stores/base.py`)

Определить протоколы/абстракции (Python 3.11+, typing.Protocol):

* `VectorStore` (общее для `srd`, `lore`, `episode`, `art`):

  ```python
  class VectorStore(Protocol):
      async def upsert(self, *, domain: str, items: list["Chunk"]) -> None: ...
      async def search(
          self,
          *,
          domain: str,
          query: str,
          k_vector: int,
          k_keyword: int | None = None,
          filters: dict | None = None,
      ) -> list["ChunkScore"]: ...
  ```

* `GraphStore` (Neo4j):

  ```python
  class GraphStore(Protocol):
      async def upsert_facts(self, facts: list["GraphFact"]) -> None: ...
      async def neighbors(self, *, node_id: str, depth: int = 1) -> "GraphNeighborhood": ...
      async def shortest_path(self, *, src_id: str, dst_id: str, max_depth: int = 4) -> "GraphPath | None": ...
  ```

Эти интерфейсы будут реализованы `pgvector_store.py` и `neo4j_graph.py`.

### 2.2 Конфигурация (`config.py`)

Единая конфигурация Memory37, синхронизированная с YAML-пресетами из главы 8.

* Задать модель:

  ```python
  @dataclass
  class EmbeddingConfig:
      model: str
      dims: int
      k_vector: int
      k_keyword: int | None
      mode: Literal["hybrid", "vector"]

  @dataclass
  class KnowledgeDomainConfig:
      store: Literal["pgvector"]
      embedding: EmbeddingConfig
  ```

* Завести пресеты по доменам (значения взять из главы 8: `dims`, `k_vector`, `k_keyword`, `mode`).

---

## 3. Модели данных (`types.py`)

Описать основные структуры в духе JSON-схем из главы 8.

### 3.1 EpisodicSummary

На основе схемы из спецификации:

* поля: `summary_id`, `campaign_id`, `party_id`, `scene_id`, `when`, `who.players/npcs`, `where`, `what`, `flags`, `relations_delta`, `notes`, `version`.

Реализовать как Pydantic v2-модель (BaseModel, `model_config = ConfigDict(extra="forbid")`).

### 3.2 NPCProfile

* поля `static` и `dynamic`, `dynamic.disposition` по партиям, массив ссылок на `summary_id` с влиянием.

### 3.3 ArtCard

* поля: `image_id`, `scene_id`, `cdn_url`, `prompt_text`, `entities`, `visual_tags`, `style`, `moderation`, `embedding`.

### 3.4 Chunk/GraphFact

* `Chunk` — единый тип для векторного индекса:

  ```python
  class Chunk(BaseModel):
      id: str
      domain: Literal["srd", "lore", "episode", "art"]
      text: str
      payload: dict
      metadata: dict
  ```

* `GraphFact` — «факт» для Neo4j (узел, связь или оба).

---

## 4. Инжест и индексация (`ingest/*`)

Инжест должен соответствовать пайплайну: normalize → chunk → embed → index.

### 4.1 `normalizer.py`

* Функции для приведения сырья к JSON-формату с ID и метаданными:

  * `normalize_srd(raw: str | dict) -> list[Chunk]`
  * `normalize_lore(raw: str | dict) -> list[Chunk]`
  * `normalize_episode(EpisodicSummary) -> Chunk`
  * `normalize_art(ArtCard) -> Chunk`

### 4.2 `chunker.py`

* Семантическое чанкирование для длинных SRD/лора:

  * режем по заголовкам/разделам/естественным блокам;
  * целимся в **500–1500 токенов** на чанк (для реализации можно пока ориентироваться на длину символов, с запасом).

### 4.3 `embedder.py`

* Адаптер вокруг OpenAI embeddings:

  * модель: `text-embedding-3-large`,
  * `dimensions` — по конфигу домена: 1536 (srd), 1024 (lore), 768–1024 (episode), 1024 (art).
* Поддержка **batch-эмбеддинга** (для пачки чанков).

### 4.4 `indexer.py`

* Высокоуровневые функции:

  ```python
  async def ingest_srd(chunks: list[Chunk]) -> None: ...
  async def ingest_lore(chunks: list[Chunk]) -> None: ...
  async def ingest_episode(summary: EpisodicSummary) -> None: ...
  async def ingest_art(card: ArtCard) -> None: ...
  ```

* Внутри: нормализация → embed → `VectorStore.upsert` (+ при необходимости `GraphStore.upsert_facts` для фактов-отношений).

---

## 5. API чтения для рантайма (`api/*`)

Эти функции — ядро Memory37 для движка и LLM-tools, должны соответствовать инструментам из главы 8.

### 5.1 `lore.py`

* `async def lore_search(query: str, *, k: int = 8, filters: dict | None = None) -> list[Chunk]`

  * домен: `lore`,
  * режим: **hybrid** (BM25 + vector, RRF),
  * k по умолчанию брать из конфигурации домена.

### 5.2 `rules.py`

* `async def rules_lookup(term: str | None = None, rule_id: str | None = None) -> list[Chunk]`

  * домен: `srd`,
  * поддержка поиска по идентификатору правила и по свободному тексту.

### 5.3 `episode.py`

* `async def session_fetch(party_id: str, *, k: int = 8) -> list[EpisodicSummary]`

  * фильтр по `party_id` и, опционально, `campaign_id`/`scene_id`; режим — чистый vector (`episode`-индекс).

### 5.4 `npc.py`

* `async def npc_profile(npc_id: str, party_id: str | None = None) -> NPCProfile | None`

  * читает профиль NPC из БД (не через vector-индекс);
  * если задан `party_id`, возвращает актуальное отношение к конкретной партии.

### 5.5 `assert_.py`

* `async def lore_assert(fact: str) -> LoreAssertResult`

  * использует `lore_search` и/или граф для проверки факта:

    * `result: Literal["true", "false", "unknown"]`
    * `sources: list[Chunk]`.

### 5.6 `art.py`

* `async def art_suggest(scene_id: str) -> ArtSuggestion`

  * ищет ArtCard по scene_id; при отсутствии — ближайшие по лору/локации.

---

## 6. Графовый слой (Neo4j) (`stores/neo4j_graph.py`)

Этап 1: базовая поддержка фактов, необходимая для:

* привязки NPC/локаций/квестов друг к другу;
* простых запросов «соседей» и коротких путей (для GraphRAG и подсказок).

### 6.1 Модель

* Узлы: минимум `Character`, `Location`, `Faction`, `Quest`, `Item`.
* Связи:

  * `(:Character)-[:LOCATED_IN]->(:Location)`
  * `(:Character)-[:ALLY_WITH]->(:Character|:Faction)`
  * `(:Character)-[:ENEMY_OF]->(:Character|:Faction)`
  * `(:Item)-[:OWNED_BY]->(:Character|:Faction)`
  * `(:Quest)-[:INVOLVES]->(:Character|:Location|:Item)`.

### 6.2 Реализация

* Обёртка над официальным драйвером Neo4j (async).
* Минимальные методы:

  * `upsert_facts(facts: list[GraphFact])`
  * `neighbors(node_id: str, depth: int = 1)`
  * `shortest_path(src_id, dst_id, max_depth=4)`.

---

## 7. Интеграция с `gateway` и LLM-tools

### 7.1 Внутренний клиент Memory37

В `gateway` (или отдельном core-пакете API) завести лёгкую обвязку:

```python
from memory37 import Memory37Client

memory = Memory37Client.from_env()
```

Инкапсулировать:

* инициализацию подключения к Postgres/pgvector;
* инициализацию Neo4j (если включён);
* загрузку конфигурации доменов.

### 7.2 LLM-tools / MCP-инструменты

Реализовать инструменты из секции 8.12 главы 8 как thin-wrappers вокруг функций Memory37:

* `rules_lookup(term|rule_id)`
* `lore_search(query, k, filters)`
* `session_fetch(party_id, k)`
* `npc_profile(npc_id, party_id)`
* `lore_assert(fact)`
* `art_suggest(scene_id)`

В gateway:

* описать schema/контракты инструментов (OpenAI tools/MCP YAML),
* подключить их к профилям LLM из главы 9 (Scene/Combat/Social/Epilogue).

---

## 8. Observability для Memory37

Синхронизация с общим стандартом наблюдаемости (OTel) из глав 5–6. 

В `observability.py`:

* вспомогательные функции для аннотирования спанов:

  * `span_attr(domain="lore", op="search", hits=8, k_vector=10, k_keyword=50, mode="hybrid")`;
* счётчики:

  * `memory37.search.requests`, `memory37.search.hits`,
  * `memory37.embed.calls`, `memory37.embed.tokens`,
  * `memory37.graph.requests`.

Это важно для последующей настройки SLO/стоимости.

---

## 9. План работ для Codex (пошагово)

### Этап 1 — каркас пакета и конфиг

1. Создать структуру `/packages/memory37`.
2. Реализовать `types.py` с Pydantic-моделями `EpisodicSummary`, `NPCProfile`, `ArtCard`, `Chunk`, `GraphFact`.
3. Реализовать `config.py` с пресетами доменов по главе 8 (dims, k, режимы).

### Этап 2 — реализация хранилищ

4. `stores/base.py`: протоколы `VectorStore`, `GraphStore`.
5. `stores/pgvector_store.py`: реализация для Postgres+pgvector.
6. `stores/neo4j_graph.py`: минимальная реализация граф-слоя.

### Этап 3 — ingestion-пайплайн

7. `ingest/normalizer.py`: функции `normalize_*`.
8. `ingest/chunker.py`: семантический чанкер.
9. `ingest/embedder.py`: обёртка над OpenAI embeddings (batch).
10. `ingest/indexer.py`: высокоуровневые `ingest_*`.

### Этап 4 — API чтения

11. `api/lore.py`: `lore_search`.
12. `api/rules.py`: `rules_lookup`.
13. `api/episode.py`: `session_fetch`.
14. `api/npc.py`: `npc_profile`.
15. `api/assert_.py`: `lore_assert`.
16. `api/art.py`: `art_suggest`.

### Этап 5 — интеграция с gateway

17. В `gateway` добавить `Memory37Client` и конфиг.
18. Подключить LLM-tools/MCP-инструменты, привязав к соответствующим функциям `memory37`.

### Этап 6 — минимальные тесты/проверки

19. Написать **smoke-тесты** (1–2 на функцию) для:

    * `lore_search` (возвращает не пустой список для заведомо существующего термина),
    * `session_fetch`,
    * `npc_profile` (чтение/апдейт отношения),
    * `ingest_episode` (пишет summary без ошибок).
20. Добавить скрипт локальной проверки, который:

    * создаёт тестовую БД,
    * делает ingest пары тестовых чанков,
    * выполняет 1–2 вызова каждого публичного API.

---

## 10. Критерии «готово»

Memory37 можно считать реализованным на этом этапе, если:

1. Пакет `packages/memory37` устанавливается и инициализируется из `gateway` без ручной настройки.
2. Существует документация (`README.md` в пакете) с описанием:

   * доменов,
   * основных API,
   * требований к БД.
3. В dev-окружении:

   * `ingest_*` успешно индексируют тестовый контент,
   * `lore_search` и `rules_lookup` возвращают релевантные чанки,
   * `session_fetch` отдаёт последние сводки по партии,
   * `npc_profile` корректно отражает изменения отношения.
4. LLM-tools `lore_search`, `rules_lookup`, `session_fetch`, `npc_profile`, `lore_assert`, `art_suggest` доступны в gateway и корректно проксируют вызовы в Memory37.
5. Метрики/спаны Memory37 появляются в общей телеметрии (OTel), хотя бы в минимальном наборе.

---

Если нужно — следующим шагом можно вынести отдельное ТЗ на **углублённый GraphRAG-слой (Neo4j)** и расширенные политики версий/TTL индексов, но для текущего этапа этого достаточно, чтобы Memory37 стал полнофункциональным, подключенным к gateway слоем знаний.
