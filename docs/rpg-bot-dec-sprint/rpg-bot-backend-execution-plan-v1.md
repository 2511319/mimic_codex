```markdown
----
slug: rpg-bot-backend-execution-plan-v1
title: "RPG-Bot Backend: План исполнения и оркестрация 4 ТЗ"
arch: "rpg-bot"
grade: "lead"
content_type: "spec"
summary: "Сопроводительный документ, который дирижирует четырьмя ТЗ (Party Sync, Memory37+GraphRAG, Genlayers+/v1/generate, Media-broker+Observability), задаёт приоритеты, порядок работ и контроль исполнения."
tags: ["rpg-bot","backend","execution-plan","codex","memory37","genlayers","media-broker","observability"]
status: "ready-for-implementation"
created: "2025-12-02"
updated: "2025-12-02"
version: "1.0.0"
reading_time: "~20 min"
outcomes:
  - "Формализована общая карта работ по backend-части RPG-Bot."
  - "Определены очередность, зависимости и точки контроля для четырёх ключевых блоков."
  - "Можно без дополнительной болтовни отдавать ТЗ в Codex/командам и контролировать прогресс по чеклистам."
----

# 0. Картина целиком

Внутри backend-части RPG-Bot сейчас есть четыре крупных направления, по которым уже подготовлены детальные ТЗ:

1. **Party Sync v1** — стабильный WebSocket-хаб кампаний, протокол, история и реплей, базовая идемпотентность.
2. **Memory37 v1 + GraphRAG + версии/TTL** — слой знаний и памяти (pgvector + Neo4j), домены SRD/Lore/Episode/NPC/Art, гибридный поиск и граф.
3. **Genlayers + `/v1/generate/*` + Memory37-контекст** — структурированная генерация сцен/боёвки/социалки/эпилога по JSON Schema, с подмешиванием knowledge-контекста.
4. **Media-broker MVP + лёгкий observability-слой** — минимальный pipeline TTS/IMG с кешем по хэшу + единая схема логов, метрик и трейсов для всех сервисов.

Этот файл:

- не повторяет сами ТЗ,
- **дирижирует** ими: задаёт:
  - порядок исполнения (waves/этапы),
  - зависимости,
  - ответственность и точки приёмки.

---

# 1. Ссылки на ТЗ (что к чему относится)

Для удобства ссылок внутри репо:

1. **Party Sync v1**

   - Файл: `rpg-bot-party-sync-v1.md`  
   - Зона: `services/party_sync`  
   - Основной исполнитель: Codex / backend-команда.

2. **Memory37 core + интеграция в gateway**

   - Файл: `rpg-bot-memory37-core-spec.md` (условное имя, фактический путь — в doc-папке проекта).  
   - Зона: `packages/memory37` + `services/gateway_api/knowledge.py` + контент-ETL.

3. **Memory37 GraphRAG + версии/TTL**

   - Файл: `rpg-bot-memory37-graph-rag-spec.md`  
   - Зона: `packages/memory37-graph` + Neo4j + version registry.

4. **Genlayers + `/v1/generate/*` + Memory37**

   - Файл: `rpg-bot-genlayers-generate-v1.md`  
   - Зона: `packages/genlayers` + `services/gateway_api/generation.py` + `routes.py`.

5. **Media-broker MVP + Observability**

   - Файл: `rpg-bot-media-broker-observability-mvp.md`  
   - Зона: `services/media_broker` + `observability/*` + glue в `gateway_api` и `party_sync`.

---

# 2. Общая логика и зависимости

Упрощённая зависимость:

- **Media-broker** и **Observability** — в основном инфраструктура, могут делаться параллельно с остальными, но лучше **поставить их в “фон”**, чтобы всё логировалось и трейсилось с первых шагов.
- **Party Sync v1** — транспортный слой, не зависит от Memory37/Genlayers. Это первая очевидная точка интеграции с внешним UI.
- **Memory37 core** — фундамент для всего, что связано с контекстом/памятью (в том числе Genlayers).
- **Genlayers + `/v1/generate/*`** — завязаны на Memory37, но не зависят от графового слоя; им достаточно v1 Memory37 (pgvector/BM25).
- **GraphRAG + версии/TTL** — расширяет Memory37, но не блокирует базовую генерацию. Важно, чтобы дизайн не ломал уже принятый API.

Итого по зависимости:

- Party Sync: независим.
- Media-broker + Observability: независимы, но полезны всем.
- Memory37 core → нужен для Genlayers.
- GraphRAG/TTL → надстройка над Memory37 core.
- Genlayers + `/v1/generate/*` → зависят от Memory37 core (и в будущем будут использовать GraphRAG).

---

# 3. Очередность (waves) и логика исполнения

Разбивка на три волны с чёткими целями.

## Wave A — “Транспорт + Инфраструктура”

**Цель:** поднять живой skeleton-бэкенд, к которому можно цеплять UI и который уже разумно логируется/трейсится.

Состав:

1. **Party Sync v1** (ТЗ: `rpg-bot-party-sync-v1.md`)

   - Реализовать:
     - `PartySession` + `PartyHub` (подключения, broadcast, история).
     - WebSocket `/ws/campaign/{campaign_id}`.
     - REST-broadcast + rate-limit.
   - Точка приёмки:
     - все тесты `services/party_sync/tests/test_party_sync.py` зелёные;
     - ручные сценарии: два клиента в одну кампанию, replay для позднего клиента.

2. **Media-broker MVP** (часть ТЗ `media-broker-observability-mvp`)

   - Довести:
     - in-memory `MediaJobManager`;
     - stub-пайплайны TTS/IMG;
     - кеш по `clientToken` и контент-хэшу.
   - Точка приёмки:
     - `pytest services/media_broker` зелёный;
     - POST двух одинаковых TTS-запросов без `clientToken` → один и тот же `jobId`.

3. **Observability baseline** (вторая часть того же ТЗ)

   - В каждом сервисе:
     - `setup_observability(app, service_name="...")` в `create_app`;
     - JSON-логи, `/metrics` (при включении), OTEL-трейсы (при включении).
   - Точка приёмки:
     - в dev-окружении `/metrics` отвечает (при `ENABLE_METRICS=true`);
     - логи в stdout в JSON с `trace_id`;
     - трейс из любых endpoints попадает в локальный OTEL-коллектор (ручная проверка).

**Результат Wave A:**  
Есть живой “каркас” backend-сервисов: party-sync, media-broker, gateway (пока без Memory37/Genlayers), плюс нормальный observability- слой. UI-команда может стабильно интегрироваться с WS и media-хуками.

---

## Wave B — “Слой знаний: Memory37 v1 + GraphRAG дизайн”

**Цель:** поставить Memory37 как отдельный слой знаний с понятными доменами и API, подготовить графовый слой и модель версий/TTL (даже если Neo4j ещё не развёрнут в проде).

Состав:

1. **Memory37 core + gateway-интеграция**  

   ТЗ: `rpg-bot-memory37-core-spec.md`

   - Реализовать:
     - `packages/memory37`:
       - `VectorStore` + `PgVectorStore`;
       - embedding-обёртка (OpenAI);
       - ingestion-пайплайн (SRD/Lore/Episode/Art).
     - API чтения:
       - `lore_search`, `rules_lookup`, `session_fetch`, `npc_profile`, `art_suggest`, `lore_assert`.
     - `gateway_api/knowledge.py`:
       - `KnowledgeService` с fallback на in-memory;
       - `/v1/knowledge/search`.
   - Точки приёмки:
     - smoke-тесты на ingest и search;
     - `/v1/knowledge/search` возвращает валидные элементы после загрузки демо-контента.

2. **GraphRAG + версии/TTL (Memory37-graph)**  

   ТЗ: `rpg-bot-memory37-graph-rag-spec.md`

   Выполняется *частично параллельно* с core (но финально — после того, как core стабилен).

   - Реализовать:
     - пакет `memory37-graph` + Neo4j-схему (узлы/рёбра, индексы);
     - `KnowledgeVersionRegistry` и alias’ы (`lore_latest`, `episode_latest`, …);
     - ingestion в граф (лоровые данные, NPC-профили, episodic summaries);
     - базовые GraphRAG-запросы (`sceneContext`, `npcSocialContext`, `questGraphContext`, `causalChain`);
     - TTL-политики (epizodes/NPC-relations/Art) и простые джобы очистки.
   - Точки приёмки:
     - графовая миграция крутится без ошибок, граф создаётся;
     - базовые GraphRAG-запросы возвращают осмысленный подграф на тестовом наборе данных;
     - alias-переключение версии отражается в запросах без перезаливки кода.

**Результат Wave B:**  
Memory37 можно использовать из gateway/ген-слоёв как стабильный источник знаний (text+graph), есть понятная тема с версиями и TTL, но Genlayers ещё не завязаны.

---

## Wave C — “Генерация: Genlayers + `/v1/generate/*` + Memory37-контекст”

**Цель:** закрыть цепочку “UI → Gateway → Genlayers → Memory37 → LLM → structured JSON response”.

Состав:

1. **Genlayers ядро**  

   ТЗ: `rpg-bot-genlayers-generate-v1.md` (часть про `packages/genlayers`)

   - Реализовать:
     - `LanguageModelProvider` / `OpenAIResponsesProvider` (JSON Schema-режим);
     - `StructuredGenerationEngine.generate` с ретраями и JSON Schema валидацией;
     - `runtime.create_engine` и CLI-обёртку `genlayers.cli generate`.
   - Точка приёмки:
     - `pytest packages/genlayers` зелёный;
     - CLI выдаёт валидный JSON под заданную схему (проверка на одной схеме).

2. **GenerationService + `/v1/generation/*`**  

   Тот же ТЗ, блок про gateway.

   - Довести:
     - `GenerationService` (инициализация engine, профили, доступность);
     - `/v1/generation/{profile}` + `/v1/generation/profiles` (тесты уже есть).
   - Точка приёмки:
     - тесты `services/gateway_api/tests/test_generation.py` проходят;
     - `/v1/generation/profiles` возвращает список профилей из `profiles.yaml`.

3. **Доменные endpoints `/v1/generate/*` + Memory37-контекст**  

   ТЗ: тот же файл, блок про новые endpoints и context-builder.

   - Реализовать:
     - `GenerationContextBuilder` на основе `KnowledgeService`;
     - `/v1/generate/scene|combat|social|epilogue`:
       - сбор frame + knowledge-контекста;
       - вызов соответствующего профиля Genlayers;
       - возврат structured JSON + метаданные knowledge-items.
   - Точка приёмки:
     - smoke-тесты:
       - при включённой Memory37 в ответе есть `knowledge_items`;
       - при выключенной — `knowledge_items` пустой, но результат возвращается.

**Результат Wave C:**  
Есть единообразный, структурированный слой генерации, который UI может дергать через `/v1/generate/*`, а Genlayers — уже завязаны на Memory37.

---

# 4. Управление и контроль исполнения

## 4.1. Формат контроля: по Waves и по ТЗ

Уровня контроля два:

1. **По Wave:**  
   В конце каждой волны — короткий “release review”:

   - какие ТЗ из волны закрыты полностью;
   - какие частично (и что именно не доделано);
   - какие блоки можно уже подключать к UI/другим системам.

2. **По конкретному ТЗ:**  
   Для каждого из 4 ТЗ используется его собственный `Definition of Done`:

   - не снимаем ТЗ, пока DoD не выполнен;
   - любые “упрощения” на данном этапе фиксируются либо:
     - отдельным пунктом “Out of scope / Post-MVP”,
     - либо TODO-списком в конце файла ТЗ.

## 4.2. Минимальный набор артефактов для контроля

Для каждой волны:

- **Wave A:**
  - лог запуска всех трёх сервисов (gateway_api, party_sync, media_broker) в dev-окружении;
  - скрин/описание проверки `/metrics` и trace-логов;
  - запись сценария “два клиента в одной кампании” (описание шагов + фактические ответы WS).

- **Wave B:**
  - список доменов Memory37 и их состояние (srd/lore/episode/npc/art — есть ли ingest, какие таблицы, какие схемы);
  - дамп тестового содержимого (минимальный JSON/YAML);
  - описание GraphRAG-подграфа на конкретной сцене (структурированный JSON).

- **Wave C:**
  - примеры ответов `/v1/generate/scene` на 2–3 разных сценария (реальный JSON, но без включения в публичные доки, если там спойлеры);
  - перечень профилей Genlayers, которые реально задействованы.

Эти артефакты можно держать в `/docs/internal/rpg-bot/backend-execution/` рядом с этим файлом.

---

# 5. Роли и разграничение ответственности (по смыслу)

Без формального RACI, но с понятной логикой:

- **Codex / автоматизированный агент в IDE:**
  - отвечает за **механическую** реализацию ТЗ по конкретным файлам:
    - Party Sync, genlayers, media-broker, часть Memory37;
  - строго следует контрактам и тестам, не меняя их без необходимости;
  - не меняет high-level архитектуру.

- **Lead backend / архитектор:**
  - отвечает за:
    - принятие решений по приоритетам (waves);
    - согласование границ ТЗ, чтобы они не конфликтовали;
    - контроль, что новые изменения не ломают контракты (OpenAPI/JSON Schema, events).

- **Контент / геймдизайн команда:**
  - подключится позже к блоку “Кампания и контент”, но ей важно иметь:
    - стабильные API Memory37 (ingest и чтение);
    - понятный GraphRAG-слой и версионность лора.

---

# 6. Резюме по порядку действий

Если свести к максимально практичному чеклисту:

1. **Сначала инфраструктурный каркас (Wave A):**
   - Party Sync v1 (WS-хаб кампаний).
   - Media-broker MVP (jobs+кеш).
   - Observability baseline (лог/метрики/трейсы во всех сервисах).

2. **Затем слой знаний (Wave B):**
   - Memory37 core + gateway-интеграция.
   - Memory37 GraphRAG + версии/TTL.

3. **Потом генерация (Wave C):**
   - Genlayers (engine + CLI).
   - GenerationService + `/v1/generation/*`.
   - `/v1/generate/*` + Memory37-контекст.

После выполнения этого плана backend-часть будет в состоянии, когда:

- UI-команда может подключать интерфейсы практически к любой части: party-sync, генерация, knowledge-просмотры, медиа.
- Контент-команда может начинать активное наполнение лора/кампаний, имея стабильные точки входа (Memory37/GraphRAG).
- Любые следующие шаги (кампания/контент, продвинутый GraphRAG, сложные эвалы и SDLC для промптов) будут строиться уже на стабильной базе.

```
