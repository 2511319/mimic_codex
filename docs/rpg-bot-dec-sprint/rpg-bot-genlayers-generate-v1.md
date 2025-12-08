````markdown
----
slug: rpg-bot-genlayers-generate-v1
title: "RPG-Bot: Genlayers + /v1/generate/* + интеграция с Memory37"
arch: "backend"
grade: "senior+"
content_type: "spec"
summary: "Доводим пакет genlayers и Gateway GenerationService до рабочей сцены, добавляем /v1/generate/* и интегрируем knowledge-контекст из Memory37."
tags: ["rpg-bot", "genlayers", "openai", "memory37", "gateway-api", "structured-outputs"]
status: "draft"
created: "2025-12-02"
updated: "2025-12-02"
version: "1.0.0"
reading_time: "25 min"
cover: ""
outcomes:
  - "Пакет genlayers доведён до полнофункционального состояния (engine, provider, runtime, CLI)."
  - "Gateway API экспонирует рабочие /v1/generate/* поверх GenerationService."
  - "Генерация сцены/комбата/социальных взаимодействий использует knowledge-контекст из Memory37."
  - "Все существующие тесты для genlayers и gateway_api проходят; добавлены минимальные smoke-тесты для новых роутов."
----

# 1. Контекст и цель

В репозитории уже есть:

- пакет `packages/genlayers` (engine структурированной генерации поверх OpenAI Responses + JSON Schema);
- сервис `services/gateway_api` с:
  - `GenerationService` (`rpg_gateway_api/generation.py`),
  - REST-обработчиками `/v1/generation/*` в `rpg_gateway_api/api/routes.py`;
- подсистема памяти `packages/memory37` и обёртка `KnowledgeService` (`rpg_gateway_api/knowledge.py`) + endpoint `/v1/knowledge/search`.

Текущие проблемы:

- `genlayers.generator`, `genlayers.providers`, `genlayers.runtime`, `genlayers.cli` частично заглушены (`...`), тесты не могут пройти;
- GenerationService не использует Memory37, а просто прокидывает сырой `prompt` в LLM;
- маршруты используют нейтральный `/v1/generation/*`, нет выделенной группы `/v1/generate/*` под игровые профили (scene/combat/social/epilogue) и knowledge-контекст.

Цель этого ТЗ:

1. Довести **genlayers** до боевого состояния с учётом глав 8 и 9 (Structured Outputs + профили).
2. Доделать **GenerationService** и REST-слой так, чтобы появился понятный публичный фасад `/v1/generate/*` над профилями.
3. Интегрировать **Memory37** как knowledge-контекст для генерации сцены (минимальный инкремент, без полного GraphRAG-оркестратора, но с учётом будущего расширения).

# 2. Область работ

## 2.1. В scope

1. **Пакет `packages/genlayers`:**
   - реализация `StructuredGenerationEngine.generate(...)` с ретраями и строгой JSON Schema-валидацией;
   - реализация `LanguageModelProvider`/`OpenAIResponsesProvider` поверх OpenAI Responses API;
   - реализация `create_engine` в `runtime.py` (инициализация engine+loader+provider);
   - завершение `cli.py` в части команды `generate` (Typer) и интеграции с `GenerationSettings`.

2. **Gateway GenerationService + API:**
   - финализировать `GenerationService` (он практически готов — важно просто не ломать интерфейс);
   - оставить `/v1/generation/*` как низкоуровневый слой;
   - добавить **доменно-ориентированные** endpoints `/v1/generate/*`, использующие:
     - выбранный профиль (`scene.v1`, `combat.v1`, `social.v1`, `epilogue.v1`);
     - knowledge-контекст от Memory37;
     - строгий structured output (JSON по `scene_response.schema.json` и др.).

3. **Интеграция с Memory37:**
   - использовать уже реализованный `KnowledgeService` как источник `KnowledgeSearchResult`;
   - добавить тонкий слой **ContextBuilder** для генерации текстового knowledge-контекста по сцене.

4. **Наблюдаемость и ошибки:**
   - логирование ключевых шагов генерации (профиль, latency, длина prompt/response, размер knowledge-контекста);
   - единый формат ошибок на уровне gateway (уже есть, не ломать).

## 2.2. Вне scope (на этом этапе)

- Полный GraphRAG (Neo4j) с traversal-профилями и сложной topological-retrieval логикой — это отдельное ТЗ.
- Нагрузка A/B, golden-сцены и сложные SDLC-практики для промптов — только учёт в API/конфиге, без реализации.
- Расширенные tools (rules_lookup, dice_roll и пр.) внутри genlayers — будут подключаться на следующем шаге.

# 3. Пакет `packages/genlayers`: требования

Цель — сделать `genlayers` минимальным, но профессиональным слоем:

- единообразная работа с профилями (`profiles.yaml`);
- строгий structured output по схемам из `contracts/jsonschema/*.schema.json`;
- OpenAI Responses API как единственный LLM-backend;
- CLI для локального вызова/отладки.

## 3.1. Структура пакета (актуальная)

Файлы:

- `src/genlayers/config.py` — `PromptProfile`, `GenerationConfig`.
- `src/genlayers/settings.py` — `GenerationSettings` (BaseSettings).
- `src/genlayers/loader.py` — `load_generation_config(...)` с lru_cache.
- `src/genlayers/schema_loader.py` — `SchemaLoader`.
- `src/genlayers/providers.py` — `LanguageModelProvider` + `OpenAIResponsesProvider` (частично заглушен).
- `src/genlayers/generator.py` — `StructuredGenerationEngine` (метод `generate` не реализован полностью).
- `src/genlayers/runtime.py` — `create_engine(...)` + `_create_provider(...)` (с `...` внутри).
- `src/genlayers/cli.py` — Typer-CLI, внутри `...`.
- Тесты: `tests/test_loader.py`, `tests/test_runtime.py`, `tests/test_genlayers_cli.py`, `tests/test_generator.py`.

**Ограничение:** новые изменения **не должны ломать публичные интерфейсы**, уже экспортируемые в `__init__.py`.

## 3.2. `LanguageModelProvider` и `OpenAIResponsesProvider`

### 3.2.1. Контракт `LanguageModelProvider`

Добавленные/зафиксированные требования:

```python
@runtime_checkable
class LanguageModelProvider(Protocol):
    """Контракт провайдера генерации текста."""

    def generate(
        self,
        prompt: str,
        temperature: float,
        max_output_tokens: int,
        schema: dict[str, Any],
        schema_name: str,
    ) -> str:
        """Синхронная генерация строки JSON по переданной JSON Schema.

        Args:
            prompt: Полный текст подсказки (system+user уже собран выше по стеку).
            temperature: Температура для модели.
            max_output_tokens: Максимум токенов для ответа.
            schema: JSON Schema для structured outputs (Draft 2020-12).
            schema_name: Короткое имя схемы (title/alias), используется для указания named-schema.

        Returns:
            Строка, которая должна быть корректным JSON-объектом.

        Raises:
            GenerationError: При ошибке общения с LLM, таймауте или невозможности получить ответ.
        """
````

### 3.2.2. Реализация `OpenAIResponsesProvider`

Задача: реализовать провайдер поверх **OpenAI Responses API**:

* использовать официальный Python-SDK (`openai` или `openai.resources.responses.Responses`);
* использовать model, api_key, timeout из `GenerationSettings`;
* вызывать **JSON-mode / response_format** или named-schema согласно выбранному способу (детали имплементации — внутри провайдера; контракт для остального кода — только строка JSON);
* на выходе привести ответ к `str` с помощью `_extract_text(output)` (функция уже частично реализована в конце файла).

Требования к поведению:

* при любой ошибке SDK/HTTP/таймаута → логировать и бросать `GenerationError("LLM provider failed", cause=exc)`;
* `generate(...)` **не должен** заниматься JSON-валидацией — только транспорт и raw-строка;
* логировать в `logger`:

  * model,
  * длину prompt (в символах, без тяжёлого подсчёта токенов),
  * max_output_tokens,
  * schema_name.

## 3.3. `StructuredGenerationEngine`

### 3.3.1. Интерфейс

Класс уже объявлен; нужно довести до следующего поведения:

```python
class StructuredGenerationEngine:
    def __init__(
        self,
        config: GenerationConfig,
        provider: LanguageModelProvider,
        schema_loader: SchemaLoader,
        max_retries: int = 1,
    ) -> None:
        ...
```

Метод:

```python
def generate(self, profile: str, prompt: str) -> dict[str, Any]:
    """Генерирует payload согласно профилю и JSON Schema.

    Raises:
        GenerationError: если после всех попыток нет валидного JSON по схеме.
    """
```

### 3.3.2. Алгоритм `generate`

1. **Поиск профиля:**

   * `profile_cfg = self._config.require_profile(profile)`
   * при `KeyError` оборачиваем в `GenerationError("Unknown profile: {profile}", cause=exc)`.

2. **Загрузка схемы:**

   * `schema = self._schema_loader.load_schema(profile_cfg.response_schema)` (или аналогично);
   * `GenerationError` при ошибке схему уже кидает `SchemaLoader` — просто не гасим.

3. **Цикл попыток (0..max_retries):**

   * `last_error: Exception | None = None`
   * для `attempt` в `range(self._max_retries + 1)`:

     1. `attempt_prompt = prompt` для `attempt == 0`;

     2. для `attempt > 0`:

        * `attempt_prompt = self._augment_prompt(prompt, last_error)` — уже реализовано как добавление hint про JSON Schema.

     3. Вызов провайдера:

        ```python
        try:
            raw = self._provider.generate(
                prompt=attempt_prompt,
                temperature=profile_cfg.temperature,
                max_output_tokens=profile_cfg.max_output_tokens,
                schema=schema,
                schema_name=profile_cfg.response_schema.replace(".json", "").replace("-", "_"),
            )
        except GenerationError as exc:
            logger.error("Ошибка провайдера на попытке %d: %s", attempt + 1, exc)
            # В этом инкременте не делаем ретраи на уровене транспорта: ошибка провайдера → сразу фейл.
            raise GenerationError("Провайдер не смог сгенерировать ответ.", cause=exc) from exc
        ```

     4. Парсинг JSON:

        ```python
        try:
            payload = json.loads(raw)
        except Exception as exc:
            last_error = exc
            logger.warning("Ответ LLM не является валидным JSON (attempt=%d): %s", attempt + 1, exc)
            continue
        ```

     5. Валидация по схеме:

        ```python
        try:
            jsonschema.validate(instance=payload, schema=schema)
        except jsonschema.ValidationError as exc:
            last_error = exc
            logger.warning("Ответ не прошёл JSON Schema validation (attempt=%d): %s", attempt + 1, exc)
            continue
        ```

     6. Если валидация прошла — вернуть `payload`.

4. **После исчерпания попыток:**

   * если `last_error` не None:

     ```python
     raise GenerationError(
         "Не удалось получить валидный JSON после повторных попыток.",
         cause=last_error,
     )
     ```

   * иначе (крайний случай):

     ```python
     raise GenerationError("Не удалось получить валидный JSON после повторных попыток.")
     ```

Метод `_augment_prompt` уже задан, его оставляем как есть.

## 3.4. `runtime.create_engine`

`create_engine(settings: GenerationSettings, provider: LanguageModelProvider | None = None) -> StructuredGenerationEngine`

Требования:

1. **Развёртывание путей:**

   * `profiles_path = _resolve_path(settings.profiles_path)`
   * `schema_root = _resolve_path(settings.schema_root)`

2. **Загрузка конфига и схем:**

   * `config = load_generation_config(profiles_path)`
   * `schema_loader = SchemaLoader(schema_root)`

3. **Провайдер:**

   * если `provider` аргумент не None — использовать его (для тестов);
   * иначе:

     ```python
     if OpenAIResponsesProvider недоступен (ImportError / AttributeError / отсутствие SDK):
         raise GenerationError("OpenAI SDK is not installed or misconfigured")
     provider = _create_provider(settings)
     ```

4. **Создание движка:**

   ```python
   return StructuredGenerationEngine(
       config=config,
       provider=provider,
       schema_loader=schema_loader,
       max_retries=settings.max_retries,
   )
   ```

5. Тест `test_create_engine_requires_openai_sdk` должен проходить: при отсутствии SDK → `GenerationError`.

## 3.5. `cli.py`

Цель — рабочая CLI-команда:

```bash
python -m genlayers.cli generate \
  --profile scene.v1 \
  --prompt "Describe the scene" \
  --profiles-path profiles.yaml \
  --schema-root contracts/jsonschema \
  --max-retries 1
```

### 3.5.1. Структура

* Typer-приложение `app = typer.Typer()`.
* Команда:

```python
@app.command()
def generate(
    profile: str = typer.Option(..., "--profile", help="Имя профиля генерации"),
    prompt: str = typer.Option(..., "--prompt", help="Текст подсказки"),
    profiles_path: Path = typer.Option(..., "--profiles-path", help="Путь к YAML с профилями"),
    schema_root: Path = typer.Option(..., "--schema-root", help="Корень JSON Schema"),
    max_retries: int = typer.Option(2, "--max-retries", help="Количество ретраев"),
) -> None:
    ...
```

### 3.5.2. Логика

1. Сформировать `GenerationSettings`:

   ```python
   settings = GenerationSettings(
       profiles_path=profiles_path,
       schema_root=schema_root,
       max_retries=max_retries,
   )
   ```

2. Вызвать `create_engine(settings)`.

3. `engine.generate(profile, prompt)` → `payload`.

4. Успех:

   ```python
   typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
   ```

5. Ошибки:

   * `ValidationError` / `GenerationError` → лог + `typer.Exit(code=1)`.

Тест `test_genlayers_cli` ожидает:

* вызов `engine.generate("scene", "Hello")`;
* корректную передачу `profiles_path`, `schema_root`, `max_retries` в `GenerationSettings`.

# 4. GenerationService и REST-слой

## 4.1. GenerationService (rpg_gateway_api/generation.py)

Класс уже почти реализован. Требования зафиксировать и **не ломать**:

```python
class GenerationService:
    def __init__(self, settings: Settings) -> None: ...
    @property
    def available(self) -> bool: ...
    def profiles(self) -> list[str]: ...
    def profile_detail(self, profile: str) -> dict[str, Any]: ...
    def generate(self, profile: str, prompt: str) -> dict[str, Any]: ...
```

Ключевые моменты:

* `_init_engine`:

  * если `OPENAI_API_KEY` пустой или `"***REDACTED***"` → логировать и **не включать** генерацию (`available=False`);
  * `profiles_path` и `schema_root` резолвятся к абсолютным путям;
  * инициализация `EngineSettings` полностью соответствует `Settings`:

    * `profiles_path=settings.generation_profiles_path`,
    * `schema_root=settings.generation_schema_root`,
    * `openai_model=settings.openai_model`,
    * `openai_api_key=settings.openai_api_key`,
    * `openai_timeout=settings.openai_timeout_seconds`,
    * `max_retries=settings.generation_max_retries`.
* `profile_detail`:

  * использует `_config` и `_schema_loader` для возврата:

    * `profile`,
    * `temperature`,
    * `maxOutputTokens`,
    * `responseSchema` (распарсенный JSON Schema).
* `generate`:

  * простой thin-wrapper над `self._engine.generate(profile, prompt)`.

## 4.2. Низкоуровневые endpoints `/v1/generation/*` (оставляем)

В `routes.py` уже есть:

* `POST /v1/generation/{profile}` — принимает `GenerationRequest` (`prompt: str`);
* `GET /v1/generation/profiles` — список профилей;
* `GET /v1/generation/profiles/{profile}` — детали профиля.

Эти endpoints:

* **не трогаем контракт**, чтобы не ломать существующие тесты и минимальные интеграции;
* используем как low-level API для внутренних тестов, отладок и, при необходимости, для бэкенд-сервисов.

## 4.3. Новые доменные endpoints `/v1/generate/*`

Добавить в `routes.py` отдельную группу тегов `["generate"]`:

### 4.3.1. Профили

Фиксируем соответствия:

* `/v1/generate/scene` → профиль `scene.v1`, схема `scene_response.schema.json`;
* `/v1/generate/combat` → `combat.v1`, `combat_response.schema.json`;
* `/v1/generate/social` → `social.v1`, `social_response.schema.json`;
* `/v1/generate/epilogue` → `epilogue.v1`, `epilogue_response.schema.json`.

### 4.3.2. Модели запросов/ответов

На первом инкременте запросы можно держать простыми, но **структурированными**:

```python
class SceneGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=2, description="Человеко-читаемое описание ситуации/контекста сцены")
    campaign_id: str | None = Field(None)
    party_id: str | None = Field(None)
    scene_id: str | None = Field(None)
    language: str | None = Field(None, description="ISO код языка, если отличен от языка партии")
    # место для будущих флагов: ab_test_variant, prompt_version и т.д.
```

Ответ:

```python
class SceneGenerateResponse(BaseModel):
    profile: str
    result: dict[str, Any]  # строго соответствует scene_response.schema.json
    knowledge_items: list[dict[str, Any]]  # метаданные по использованным кускам лора
```

Аналогично для combat/social/epilogue (при желании можно переиспользовать общий `GenerateResponse`).

### 4.3.3. Логика endpoints

На уровне роутера:

```python
@router.post("/v1/generate/scene", tags=["generate"])
def generate_scene(
    payload: SceneGenerateRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> SceneGenerateResponse:
    service: GenerationService = request.app.state.generation_service
    knowledge: KnowledgeService | None = getattr(request.app.state, "knowledge_service", None)
    ...
```

Шаги:

1. Проверка наличия/доступности `GenerationService` и `KnowledgeService`:

   * если `generation_service` недоступен → `503 Generation service unavailable`;
   * если knowledge недоступен — **не падаем**, просто генерируем без лора (лог + флаг в ответе).

2. Формирование knowledge-контекста через отдельный helper (см. §5):

   ```python
   context, used_items = build_scene_context(payload, knowledge)
   ```

3. Формирование итогового prompt для genlayers:

   * конкатенировать:

     * краткий system-header (может быть зашит в промптах/профилях, здесь только user-часть),
     * `context` (SCENE/LORE/NPC/ART),
     * `payload.prompt`.

   Пример структуры строки (на уровне ТЗ, без конкретного текста):

   ```text
   [SCENE FRAME]
   campaign_id: <...>
   party_id: <...>
   scene_id: <...>

   [KNOWLEDGE]
   1) <snippet 1>
   2) <snippet 2>
   ...

   [REQUEST]
   <payload.prompt>
   ```

4. Вызов:

   ```python
   result = service.generate("scene.v1", final_prompt)
   ```

5. Возврат:

   ```python
   return {
       "profile": "scene.v1",
       "result": result,
       "knowledge_items": [item.model_dump() for item in used_items],
   }
   ```

Ошибки `GenerationError` → 502 `Bad Gateway`, как и в существующем `/v1/generation/{profile}`.

Аналогичный паттерн для `/v1/generate/combat`, `/v1/generate/social`, `/v1/generate/epilogue` (на первом шаге можно использовать тот же `SceneGenerateRequest`, позже развести по доменным полям).

# 5. Интеграция с Memory37 (knowledge-контекст)

## 5.1. Исходные компоненты

Уже есть:

* `KnowledgeService(Settings)` (`knowledge.py`), умеет:

  * ETL из YAML (`data/knowledge/*.yaml`) через Memory37;
  * при наличии `KNOWLEDGE_DATABASE_URL` — использовать `PgVectorStore` поверх PostgreSQL+pgvector;
  * search: `KnowledgeService.search(q: str, top_k: int) -> list[KnowledgeSearchResult]`;
* конфиг `config/knowledge/knowledge.yaml` с доменами `srd`, `lore`, `campaigns`, `npcs`, `artcards` (пока используется частично).

## 5.2. ContextBuilder для генерации

Добавить модуль (варианты):

* либо `rpg_gateway_api/generation_context.py`,
* либо расширить `generation.py` вспомогательными функциями (предпочтительно отдельный модуль для чистоты).

### 5.2.1. Интерфейс

```python
class GenerationContextBuilder:
    def __init__(self, knowledge: KnowledgeService | None) -> None: ...

    def build_scene_context(
        self,
        payload: SceneGenerateRequest,
        top_k: int = 6,
    ) -> tuple[str, list[KnowledgeSearchResult]]:
        """Возвращает текстовый блок контекста и список использованных knowledge-элементов."""
```

### 5.2.2. Алгоритм `build_scene_context`

1. Если `knowledge is None` или `not knowledge.available`:

   * вернуть `("", [])`.

2. Построить поисковый запрос `q`:

   * если есть `payload.scene_id` → приоритет дать точному поиску по id в будущем; на первом шаге можно просто включить id в текст:

     * `q = f"{payload.scene_id or ''} {payload.prompt}"`.
   * добавить `campaign_id`, `party_id` при наличии.

3. Вызвать `knowledge.search(q, top_k=top_k)`.

4. Собрать текстовый блок:

   ```text
   [KNOWLEDGE]
   - <item1.content_snippet>
   - <item2.content_snippet>
   ...
   ```

5. Вернуть `(context_text, results)`.

### 5.2.3. Расширяемость под GraphRAG

Важно: не завязывать `GenerationService` напрямую на внутренние типы Memory37.

* `GenerationContextBuilder` должен оперировать **интерфейсом** `KnowledgeService` (метод `search` и модель `KnowledgeSearchResult`).
* В будущем, когда появится Neo4j-слой/GraphRAG, `KnowledgeService` либо:

  * сам начнёт использовать GraphRAG внутри `search`, либо
  * появится новый сервис, а `GenerationContextBuilder` будет подменён в DI.

Тем самым /v1/generate/* уже спроектирован под knowledge-контекст без жёсткой привязки к реализации.

## 5.3. Встраивание в маршруты

В `routes.py`:

* внутри новых `/v1/generate/*`:

  ```python
  knowledge_service = getattr(request.app.state, "knowledge_service", None)
  context_builder = GenerationContextBuilder(knowledge_service)
  context, used_items = context_builder.build_scene_context(payload)
  final_prompt = _compose_prompt(payload, context)
  result = generation_service.generate("scene.v1", final_prompt)
  ```

* `used_items` → в ответ.

# 6. Конфигурация и окружение

## 6.1. Genlayers / Env

Используем уже существующие настройки:

* `GENLAYERS_profilesPath` / `GENLAYERS_schemaRoot` / `GENLAYERS_openaiModel` / `GENLAYERS_openaiApiKey` / `GENLAYERS_openaiTimeout` / `GENLAYERS_maxRetries` — через `GenerationSettings`.

Для Gateway:

* `GENERATION_PROFILES_PATH` (пример: `profiles.yaml`);
* `GENERATION_SCHEMA_ROOT` (пример: `contracts/jsonschema`);
* `GENERATION_MAX_RETRIES` (обычно 1–2);
* `OPENAI_MODEL` (например, `gpt-4.1`);
* `OPENAI_API_KEY` (секрет);
* `OPENAI_TIMEOUT_SECONDS` (по умолчанию 120).

## 6.2. Knowledge / Env

* `KNOWLEDGE_SOURCE_PATH` — путь до YAML (`data/knowledge/sample.yaml` / `data/knowledge/campaigns/*.yaml`);
* `KNOWLEDGE_DATABASE_URL` — строка подключения к PostgreSQL+pgvector (опц.);
* `KNOWLEDGE_USE_OPENAI` — флаг использования OpenAI для embedding/rerank;
* `KNOWLEDGE_OPENAI_EMBEDDING_MODEL`, `KNOWLEDGE_OPENAI_RERANK_MODEL`.

# 7. Наблюдаемость и ошибки

## 7.1. Логирование

Обязательные поля логов при генерации:

* `profile` (scene.v1/combat.v1/...),
* `prompt_len` (символы),
* `knowledge_items` (кол-во и, опционально, ids),
* `retries_used` (0..max_retries),
* `success`/`failure` и тип ошибки (`schema_validation`, `json_parse`, `provider_error`).

## 7.2. Ошибки REST

Сохраняем общую модель:

* `503` — service unavailable (generation или knowledge);
* `404` — неизвестный профиль;
* `502` — ошибки LLM/structured generation (оборачиваем текст ошибки, не светим stacktrace).

# 8. План работ для Codex (пошагово)

## 8.1. Genlayers

1. **providers.py**

   * реализовать интерфейс `LanguageModelProvider`;
   * дописать `OpenAIResponsesProvider.generate`:

     * инициализация клиента;
     * вызов Responses API с JSON Schema;
     * сбор текста через `_extract_text`;
     * обработка ошибок → `GenerationError`.

2. **generator.py**

   * реализовать `StructuredGenerationEngine.__init__` (если не доделан) и `generate` по алгоритму §3.3.2.

3. **runtime.py**

   * реализовать `create_engine` и `_create_provider` по §3.4;
   * `_resolve_path` оставить как есть (уже реализован).

4. **cli.py**

   * реализовать Typer-команду `generate` по §3.5.

5. **Прогнать тесты пакета:**

   ```bash
   cd packages/genlayers
   pytest
   ```

## 8.2. Gateway GenerationService + /v1/generate/*

1. **generation_context.py** (новый модуль) либо расширение `generation.py`:

   * реализовать `GenerationContextBuilder` по §5.2.

2. **routes.py**

   * добавить модели `SceneGenerateRequest`, `SceneGenerateResponse` (и при необходимости аналоги для других профилей);
   * добавить endpoints:

     * `POST /v1/generate/scene`,
     * `POST /v1/generate/combat`,
     * `POST /v1/generate/social`,
     * `POST /v1/generate/epilogue`.
   * внутри использовать `GenerationService` + `KnowledgeService` + `GenerationContextBuilder`.

3. **Минимальные тесты:**

   В `services/gateway_api/tests/test_generation.py`:

   * smoke-тест `POST /v1/generate/scene`:

     * подменить `generation_service` на `DummyGenerationService` (аналог существующего);
     * подменить `knowledge_service` на заглушку, возвращающую пару `KnowledgeSearchResult`;
     * проверить:

       * 200 OK;
       * `profile` в ответе;
       * есть `result["title"]` (согласно DummyGenerationService);
       * массив `knowledge_items` не пустой.

   * тест на недоступный `generation_service` → 503.

4. **Гонка тестов gateway_api:**

   ```bash
   cd services/gateway_api
   pytest
   ```

# 9. Definition of Done

1. **Genlayers:**

   * Все тесты в `packages/genlayers/tests` зелёные.
   * CLI `python -m genlayers.cli generate ...` возвращает валидный JSON, проходящий валидацию соответствующей JSON Schema.
   * При отсутствии OpenAI-SDK `create_engine` кидает `GenerationError` (тест покрывает).

2. **Gateway /v1/generation/*:**

   * Существующие тесты в `services/gateway_api/tests/test_generation.py` проходят без изменений контракта.

3. **Gateway /v1/generate/*:**

   * Добавлены и работают четыре endpoint: `scene`, `combat`, `social`, `epilogue`.
   * В `POST /v1/generate/scene`:

     * при включённом `KnowledgeService` в ответе присутствуют `knowledge_items` с хотя бы одним элементом;
     * при выключенном `KnowledgeService` endpoint всё равно отвечает 200, но `knowledge_items` пустой.
   * Для всех новых endpoints есть хотя бы по одному smoke-тесту.

4. **Интеграция с Memory37:**

   * `KnowledgeService` используется только через публичный интерфейс (поиск);
   * Генерация сцены в логах фиксирует:

     * профиль,
     * длину prompt,
     * количество knowledge-элементов.

5. **Операционная готовность:**

   * `/config` отражает состояние:

     * `knowledge_state` — enabled/disabled по факту загрузки памяти;
     * `generation_state` — enabled/disabled по факту инициализации Genlayers.
   * Документация по новым эндпоинтам (`/v1/generate/*`) добавлена в `contracts/openapi/rpg-bot.yaml` (минимально — paths + схемы запрос/ответ).

```markdown
```
