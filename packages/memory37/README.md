# Memory37 Core (каркас)

Каркас реализации Memory37 под спецификацию Wave B.

## Доменные сущности
- `types.EpisodicSummary`, `NPCProfile`, `ArtCard`, `Chunk/ChunkScore`, `GraphFact`.

## Инжест (normalize → chunk → embed → index)
- `ingest/normalizer.py` — normalize_srd/lore/episode/art.
- `ingest/chunker.py` — простое чанкирование по символам для лора.
- `ingest/embedder.py` — обёртка над OpenAI/TF-вектором.
- `ingest/indexer.py` — ingest_srd/lore/episode/art → embed → `VectorStore.upsert`.

## Сторы
- `stores/base.py` — протоколы `VectorStore`/`GraphStore`.
- `stores/pgvector_store.py` — адаптер к существующему `PgVectorStore` (vector-only, payload.embedding ожидается).

## API (минимальные заглушки, требуется доработка)
- `api/lore.py`: `lore_search(store, query, k)` — через `store.search`.
- `api/rules.py`: `rules_lookup(store, term|rule_id, k)` — через `store.search`.
- `api/episode.py` / `api/npc.py` / `api/art.py` / `api/assert_.py` — подключены к VectorStore, но требуют нормализации данных и связки с реальным хранилищем (pgvector/BM25).

## Версионирование/TTL
- `versioning.py` — реестр версий/алиасов; `knowledge_version_id` в `KnowledgeItem` уже поддержан.
- Для полноценной поддержки нужно добавить столбец/фильтр `knowledge_version_id` в pgvector/BM25 таблицы и CLI флаги.

## План доработок
- Заполнить API чтения (session_fetch, npc_profile, lore_assert, art_suggest) через реальное хранилище.
- Добавить embedder вызовы и pgvector/BM25 схемы с `knowledge_version_id`.
- Интегрировать core API в gateway (KnowledgeService) вместо старого retriever.

## Быстрый старт (Wave B)

- In-memory ingest и поиск:
  ```bash
  PYTHONPATH=packages/memory37/src ^
  python -m memory37.cli ingest-file data/knowledge/sample.yaml --dry-run --knowledge-version-id=kv_demo

  python -m memory37.cli search "moon ruins" --knowledge-file data/knowledge/sample.yaml --dry-run
  ```

- Ingest в Postgres+pgvector (нужен psycopg):
  ```bash
  python -m memory37.cli ingest-file data/knowledge/sample.yaml --dsn $MEMORY37_DATABASE_URL --knowledge-version-id=kv_stage
  ```

- Версии и TTL:
  - `--knowledge-version-id` прокидывается в metadata и колонку `knowledge_version_id`.
  - `load_knowledge_items_from_yaml(..., ttl_days=N)` добавляет `expires_at`, `PgVectorWrapper.cleanup_expired()` удаляет просроченные записи.

- Обёртки стора:
  - `InMemoryVectorStore` — гибридный поиск (vector+lexical) для CLI/тестов.
  - `PgVectorWrapper` — pgvector + авто-embedding через OpenAI/TF embedder.
