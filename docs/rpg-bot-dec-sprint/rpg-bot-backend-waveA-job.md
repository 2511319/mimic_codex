----
slug: rpg-bot-backend-waveA
title: "RPG-Bot Backend Wave A: Party Sync v1, Media-broker MVP, Observability baseline"
wave: "A"
priority: "P0"
branch: "feat/rpg-backend-waveA"
repo_root: "D:\\project\\mimic_codex"
specs:
  - "docs/rpg-bot-backend-execution-plan-v1.md"
  - "docs/rpg-bot-party-sync-v1.md.md"
  - "docs/rpg-bot-media-broker-observability-mvp.md"
services:
  - "services/party_sync"
  - "services/media_broker"
  - "services/gateway_api"
status: "ready-for-codex"
outcomes:
  - "Стабильный Party Sync v1 (WS-хаб кампаний + REST-broadcast) по спецификации."
  - "Media-broker MVP с stub-пайплайнами TTS/IMG и кешированием по clientToken и контент-хэшу."
  - "Единый observability-слой (трейсы/метрики/JSON-логи) во всех трёх сервисах."
----

## Цель Wave A

Поднять рабочий «каркас» backend:

- Party Sync v1 — транспорт и синхронизация партий.
- Media-broker — минимальный медиа-сервис для TTS/изображений.
- Observability — единая система логов, метрик и трейсинга.

Это первая волна. Никакие задачи из Wave B и Wave C выполнять не нужно.

---

## Контекст и документация

Перед началом прочитать:

1. `docs/rpg-bot-backend-execution-plan-v1.md`  
   - разделы про Wave A, зависимость сервисов.

2. `docs/rpg-bot-party-sync-v1.md.md`  
   - контракт Party Sync v1: протоколы, состояния, события, DoD.

3. `docs/rpg-bot-media-broker-observability-mvp.md`  
   - Media-broker MVP: job manager, кеширование, API;
   - Observability baseline: OTel/Prometheus/JSON-логи.

---

## Область работ

### 1. Party Sync v1 (services/party_sync)

**Что нужно сделать:**

- Реализовать всё, что описано в `rpg-bot-party-sync-v1.md.md`:

  1. `PartySession` / `PartyHub`:
     - подключение/отключение по WebSocket,
     - хранение состояния сессии/участников,
     - рассылка событий по кампании,
     - базовая история и реплей для поздних подключений.

  2. WebSocket endpoint:
     - `GET /ws/campaign/{campaign_id}` (путь из ТЗ),
     - при подключении клиент получает:
       - текущий snapshot состояния,
       - далее поток событий.

  3. REST-broadcast:
     - эндпоинт(ы) для отправки события в партию от backend/UI,
     - идемпотентность по eventId (если оговорено в ТЗ),
     - простой rate-limit (как в спецификации).

**Ограничения:**

- Не ломать контракты, описанные в ТЗ и уже существующих тестах.
- Не менять формат входных/выходных JSON, кроме прямо прописанных в ТЗ.

**Тесты и проверки:**

- Запустить:  
  `pytest services/party_sync`
- Ручной сценарий (описать в отчёте):
  - два тестовых клиента подключаются к одной кампании;
  - один шлёт 2–3 события;
  - второй подключается позже и получает:
    - историю,
    - последующие события в real-time.

---

### 2. Media-broker MVP (services/media_broker)

**Что нужно сделать:**

- На базе `rpg-bot-media-broker-observability-mvp.md`:

  1. Довести `MediaJobManager` до рабочего состояния:
     - очередь jobs,
     - воркеры,
     - корректные статусы: `queued`, `processing`, `succeeded`, `failed`,
     - методы `enqueue`, `get_job`, `start/stop`.

  2. Реализовать stub-пайплайны:
     - TTS:
       - вход: payload с полями `text`, `voice?`, `speed?`, `model?`;
       - выход: `{"audioUrl", "durationMs", "voice"}` (см. ТЗ).
     - Image:
       - вход: `prompt`, `style?`, `seed?`, `width?`, `height?`, `model?`, `postproc?`;
       - выход: `{"cdnUrl", "style", "width", "height"}` (см. ТЗ).

  3. Кеширование:
     - Идемпотентность по `clientToken` (уже есть в зачатке — сохранить).
     - Добавить кеш по **контент-хэшу**:
       - для `tts`: хэш от (jobType, text, voice, speed, model);
       - для `image`: хэш от (jobType, prompt, style, seed, width, height, model, postproc).
     - Структура: `self._jobs_by_hash: Dict[str, job_id]`.
     - Поведение:
       - если приходит запрос без clientToken, но с тем же содержимым, и job ещё в истории — вернуть существующую.

**Тесты и проверки:**

- Запустить:  
  `pytest services/media_broker`
- Добавить тест:
  - два POST `/v1/media/jobs` с одинаковым `jobType="tts"` и одинаковым payload, **без `clientToken`**;
  - ответ должен иметь один и тот же `jobId`.

---

### 3. Observability baseline (gateway_api, party_sync, media_broker)

**Что нужно сделать:**

- Привести все три сервиса к единому паттерну observability, как описано в `rpg-bot-media-broker-observability-mvp.md` и главе 6 мастер-документа.

1. В каждом сервисе (`services/gateway_api`, `services/party_sync`, `services/media_broker`):

   - Убедиться, что существует функция `setup_observability(app, service_name=...)` в `observability.py`.
   - В `create_app()` вызывается **ровно один раз**:
     - `setup_observability(app, service_name="<имя-сервиса>")`.
   - Имена сервисов стандартизировать:
     - `"gateway-api"`, `"party-sync"`, `"media-broker"`.

2. Логи:

   - Все сервисы используют `observability/logging.json` как конфиг.
   - Логи — в JSON-формате, содержат `trace_id`.
   - Middleware `inject_trace_id` и `http_logger` подключены и одинаково работают.

3. Метрики:

   - При `ENABLE_METRICS=true` во всех трёх сервисах доступен `/metrics` (Prometheus Instrumentator).
   - При выключенном флаге сервисы работают без ошибок.

4. Трейсинг:

   - При `ENABLE_OTEL=true` и настроенном OTLP endpoint включается FastAPI-инструментация и Requests-инструментация.
   - Ошибки при инициализации OTel не валят сервис, только логируются.

**Проверки:**

- Локально:
  - запустить каждый сервис с `ENABLE_METRICS=true`;
  - убедиться, что `GET /metrics` возвращает данные.
- Проверить, что в логах HTTP-запросов есть `trace_id`.

---

## Границы ответственности

В рамках Wave A:

- Не менять код `packages/memory37`, `packages/genlayers`, не трогать `/v1/generate/*` и Memory37-интеграции.
- Не вводить внешние зависимости, кроме действительно необходимых для observability (если они уже заложены в ТЗ).

---

## Definition of Done (Wave A)

Wave A можно считать завершённой, если:

1. Все тесты `services/party_sync` и `services/media_broker` проходят.
2. Party Sync:
   - WS-хаб корректно обслуживает несколько клиентов;
   - позднее подключение получает историю и новые события.
3. Media-broker:
   - POST `/v1/media/jobs` с одинаковыми payload (tts/image) без `clientToken` возвращает один и тот же `jobId`, пока job хранится в истории;
   - идемпотентность по `clientToken` работает.
4. Observability:
   - `/metrics` работает при `ENABLE_METRICS=true`;
   - JSON-логи с `trace_id` пишутся во всех сервисах;
   - `setup_observability` вызывается ровно один раз на сервис.

В отчёте по выполнению Wave A указать:

- список изменённых файлов по каждому сервису;
- какие тесты запускались;
- кратко: для каждого пункта DoD — выполнено/нет и комментарий.
