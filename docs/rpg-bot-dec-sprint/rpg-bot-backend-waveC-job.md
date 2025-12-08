----
slug: rpg-bot-backend-waveC
title: "RPG-Bot Backend Wave C: Genlayers + /v1/generate/* + Memory37-контекст"
wave: "C"
priority: "P0"
branch: "feat/rpg-backend-waveC"
repo_root: "D:\\project\\mimic_codex"
specs:
  - "docs/rpg-bot-backend-execution-plan-v1.md"
  - "docs/rpg-bot-genlayers-generate-v1.md"
  - "docs/rpg-bot-memory37-core-spec.md"
services:
  - "packages/genlayers"
  - "services/gateway_api"
status: "ready-for-codex"
outcomes:
  - "Genlayers реализован как рабочий движок структурированной генерации (OpenAI Responses + JSON Schema)."
  - "GenerationService и /v1/generation/* стабилизированы и используют Genlayers."
  - "Добавлены доменные /v1/generate/* endpoints, использующие Memory37 как knowledge-контекст."
----

## Цель Wave C

Закрыть полный путь:

UI → `/v1/generate/*` → GenerationService (Genlayers) → Memory37 → LLM → структурированный JSON-ответ.

Wave C выполняется **после успешного завершения Wave B**.

---

## Контекст и документация

Прочитать:

1. `docs/rpg-bot-backend-execution-plan-v1.md` — разделы Wave C.
2. `docs/rpg-bot-genlayers-generate-v1.md` — ТЗ по Genlayers и `/v1/generate/*`.
3. При необходимости — `docs/rpg-bot-memory37-core-spec.md` (часть про `KnowledgeService`).

---

## Область работ

### 1. Genlayers core (packages/genlayers)

**Что сделать:**

- В `providers.py`:
  - интерфейс `LanguageModelProvider`;
  - реализация `OpenAIResponsesProvider.generate` поверх OpenAI Responses API:
    - принимает `prompt`, `temperature`, `max_output_tokens`, `schema`, `schema_name`;
    - вызывает Responses API в JSON/structured режиме;
    - возвращает строку с JSON;
    - ошибки → `GenerationError`.

- В `generator.py`:
  - реализовать `StructuredGenerationEngine.__init__`;
  - реализовать `generate(profile, prompt)`:
    - поиск профиля,
    - загрузка JSON Schema,
    - вызов провайдера,
    - `json.loads`,
    - `jsonschema.validate`,
    - ретраи с `_augment_prompt` при невалидном JSON/валидации,
    - по истечении попыток → `GenerationError`.

- В `runtime.py`:
  - реализовать `create_engine(settings, provider=None)`:
    - резолвинг `profiles_path`, `schema_root`,
    - загрузка `GenerationConfig` и `SchemaLoader`,
    - создание провайдера (если не передан),
    - возврат `StructuredGenerationEngine`.
  - `_create_provider()` — создание `OpenAIResponsesProvider` из `GenerationSettings`.

- В `cli.py`:
  - Typer-приложение с командой `generate`:
    - параметры: `--profile`, `--prompt`, `--profiles-path`, `--schema-root`, `--max-retries`;
    - создаёт `GenerationSettings`, engine через `create_engine`;
    - вызывает `engine.generate(profile, prompt)` и печатает JSON.

**Тесты:**

- `pytest packages/genlayers`.

---

### 2. GenerationService и /v1/generation/* (services/gateway_api)

**Что сделать:**

- В `rpg_gateway_api/generation.py`:

  - Убедиться, что `GenerationService`:
    - инициализирует Genlayers engine при наличии `OPENAI_API_KEY`;
    - корректно отражает `available`;
    - отдаёт список профилей и details (`profile_detail`);
    - метод `generate(profile, prompt)` — thin-wrapper над `engine.generate`.

- В API-роутах:

  - Проверить/дописать:
    - `POST /v1/generation/{profile}` (в запросе только `prompt`);
    - `GET /v1/generation/profiles`;
    - `GET /v1/generation/profiles/{profile}`.

- Не менять публичный контракт этих эндпоинтов.

**Тесты:**

- `pytest services/gateway_api -k generation` (или весь пакет).

---

### 3. Доменные эндпоинты /v1/generate/* + Memory37-контекст

**Что сделать:**

- Добавить `GenerationContextBuilder` (отдельный модуль или часть `generation.py`):

  - В конструктор передаётся `KnowledgeService | None`.
  - Метод `build_scene_context(payload: SceneGenerateRequest, top_k: int = 6)`:
    - если `KnowledgeService` недоступен → вернуть `("", [])`;
    - иначе:
      - собрать запрос `q` из `scene_id`, `campaign_id`, `party_id`, `prompt`;
      - вызвать `knowledge_service.search(q, top_k)`;
      - вернуть:
        - текстовый контекст `[KNOWLEDGE] ...` из топ-N сниппетов,
        - список `KnowledgeSearchResult`.

- Добавить модели запросов/ответов:

  - `SceneGenerateRequest`:
    - `prompt: str`;
    - `campaign_id?: str`;
    - `party_id?: str`;
    - `scene_id?: str`;
    - `language?: str`.

  - `SceneGenerateResponse`:
    - `profile: str`;
    - `result: dict[str, Any]` (структура из `scene_response.schema.json`);
    - `knowledge_items: list[dict[str, Any]]`.

- Добавить эндпоинты:

  - `POST /v1/generate/scene`:
    - использует профиль `scene.v1`;
    - строит `context` через `GenerationContextBuilder`;
    - собирает финальный prompt (frame + knowledge + user prompt);
    - вызывает `GenerationService.generate("scene.v1", final_prompt)`;
    - возвращает `SceneGenerateResponse`.

  - Аналогичный паттерн для:
    - `/v1/generate/combat` (профиль `combat.v1`);
    - `/v1/generate/social` (профиль `social.v1`);
    - `/v1/generate/epilogue` (профиль `epilogue.v1`);
    - на первом этапе можно переиспользовать тот же request/response с разными профилями.

**Проверки:**

- При включённой Memory37:
  - `POST /v1/generate/scene` возвращает:
    - осмысленный `result`,
    - непустой `knowledge_items`.

- При отключённой Memory37:
  - endpoint не падает;
  - `knowledge_items` пустой, генерация идёт без контекста (или с минимальным).

- Тесты:
  - добавить 1–2 smoke-теста на `/v1/generate/scene` (с подменой GenerationService/KnowledgeService на заглушки).

---

## Границы ответственности Wave C

- Не менять Memory37 core/GraphRAG, кроме необходимых адаптаций под context-builder (лучше через публичный `KnowledgeService`).
- Не менять Party Sync и Media-broker в рамках этой волны.

---

## Definition of Done (Wave C)

Wave C завершена, если:

1. Все тесты `packages/genlayers` зелёные.
2. Все тесты `services/gateway_api`, связанные с generation, зелёные.
3. `/v1/generation/*` работают поверх Genlayers (engine реально используется).
4. `/v1/generate/scene|combat|social|epilogue`:
   - доступны и возвращают структурированный JSON по схемам;
   - при включённой Memory37 подмешивают knowledge-контекст;
   - при отключённой Memory37 продолжают работать.

В отчёте указать:

- какие профили реально используются (`scene.v1`, `combat.v1`, ...);
- примеры 1–2 ответов `/v1/generate/scene` (без лишних спойлеров);
- какие тесты запускались и результат.
