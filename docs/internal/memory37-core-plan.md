# Memory37 core — план доводки (Wave B)

## Что уже есть
- Каркас типов (EpisodicSummary, NPCProfile, ArtCard, Chunk/ChunkScore, GraphFact).
- Инжест-пайплайн (normalize → chunk → embed → index) и протоколы VectorStore/GraphStore.
- Версии/aliases (registry) и knowledge_version_id в KnowledgeItem; retriever фильтрует метаданные.

## Что нужно доделать
1. **API чтения** — реализовать настоящие функции:
   - lore_search/rules_lookup через pgvector/BM25 с embedder.
   - session_fetch (чтение эпизодов) и npc_profile (чтение/обновление динамики).
   - lore_assert (использует lore_search/graph), art_suggest (по scene_id/лору).
2. **Хранилище**:
   - Добавить knowledge_version_id в таблицы pgvector/BM25, CLI опции alias/version.
   - Настроить embedder (OpenAI/локальный) и ingestion CLI.
3. **Интеграция в gateway**:
   - Обновить KnowledgeService на новое API (search/lookup/profile/assert).
   - Подготовить smoke-скрипты ingest+search.
4. **TTL/очистка**:
   - Поля expires_at для эпизодов/динамических отношений; cron/APOC или python-скрипт для очистки.
5. **Тесты**:
   - Smoke на ingest_lore/lore_search, npc_profile, session_fetch.
   - e2e: gateway /v1/knowledge/search на демо-данных.

## Быстрый порядок действий
- Реализовать pgvector ingestion с embedder и version_id.
- Поднять minimal DB schema (vector table + version_id).
- Переписать KnowledgeService на новые API.
- Добавить smoke CLI/README для core (ingest YAML, search).
