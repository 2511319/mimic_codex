````markdown
----
slug: rpg-bot-media-broker-observability-mvp
title: "RPG-Bot: Media-broker MVP и лёгкий observability-слой"
arch: "backend"
grade: "senior+"
content_type: "spec"
summary: "Минимальный, но реалистичный медиа-пайплайн (images/TTS) с кешом по хэшу и единый лёгкий observability-слой (трейсы/метрики/логи) для всех сервисов."
tags: ["rpg-bot", "media-broker", "tts", "images", "observability", "otel", "prometheus", "logging"]
status: "draft"
created: "2025-12-02"
updated: "2025-12-02"
version: "1.0.0"
reading_time: "25 min"
cover: ""
outcomes:
  - "Media-broker реализует /v1/media/jobs с рабочим in-memory job-менеджером, stub-пайплайном для TTS/IMG и кешом по контент-хэшу."
  - "Поддерживается идемпотентность запросов через clientToken и контент-хэш, как описано в Главе 5 (кеши и TTL)."
  - "Во всех сервисах (gateway_api, party_sync, media_broker) настроен единый лёгкий observability-слой: OpenTelemetry-трейсы, Prometheus-метрики, структурированные JSON-логи."
  - "Телеметрия включается/отключается только переменными окружения, код сервисов остаётся тонким и единообразным."
----

# 1. Контекст и цель

В репозитории уже есть:

- `services/media_broker`:
  - `app.py` — фабрика FastAPI-приложения, CORS, middleware для trace_id, http-логгер;
  - `api/routes.py` — `/health`, `POST /v1/media/jobs`, `GET /v1/media/jobs/{job_id}`;
  - `manager.py` — `MediaJobManager` с очередью, in-memory хранилищем, stub-результатами для `tts|stt|image|avatar`;
  - `models.py` — `MediaJobRequest`, `MediaJobRecord`, `MediaJobResponse`;
  - `observability.py` — `setup_observability(..., service_name="media-broker")`;
  - `rate_limit.py` — простой token-bucket limiter для POST /v1/media/jobs;
  - тест `services/media_broker/tests/test_media_broker.py` (проверяет идемпотентность по `clientToken` и 202).

- `services/gateway_api`, `services/party_sync`:
  - собственные `observability.py`;
  - middleware `inject_trace_id` + http-логгеры;
  - общий лог-конфиг `observability/logging.json` и описания в Главе 6.

Цель этого ТЗ:

1. Довести `Media-broker` до **MVP медиа-пайплайна**:
   - минимальный, но рабочий жизненный цикл jobs;
   - stub-генерация для TTS и изображений;
   - **кеш по контент-хэшу** (TTS/IMG) + идемпотентность по `clientToken`.

2. Зафиксировать и добить **лёгкий observability-слой**:
   - OTel-трейсы, Prometheus-метрики и JSON-логи;
   - единая конфигурация и паттерн подключения по всем сервисам;
   - минимум точек контакта в коде сервисов ("по одному месту" на сервис).

# 2. Media-broker MVP

## 2.1. Область работ

**В scope:**

- Завершение и стабилизация поведения:
  - `MediaJobManager` (очередь, workers, job lifecycle);
  - `MediaJobRequest/Record/Response` (структура и алиасы);
  - `POST /v1/media/jobs`, `GET /v1/media/jobs/{job_id}`.
- Stub-пайплайн:
  - TTS: генерация fake `audioUrl`, `durationMs`, `voice`;
  - IMG: генерация fake `cdnUrl`, `style`, `width/height`.
- **Кеширование по контент-хэшу**:
  - TTS: `hash(text + voice + speed + model)`;
  - IMG: `hash(prompt + style + seed + size + model + postproc)`;
  - корректная работа как с `clientToken`, так и без него.
- Минимальная конфигурация через `Settings`.

**Out of scope (на этот этап):**

- Реальная интеграция с внешними провайдерами (OpenAI Images/TTS, ElevenLabs и т.п.);
- Поддержка STT/Avatar в прод-качестве (остаются stub’ами);
- Персистентное хранилище jobs (PostgreSQL, Redis) — пока только in-memory;
- Сложные SLA/квоты/оплата медиа (только базовый rate-limit).

## 2.2. Модели и контракты

### 2.2.1. `MediaJobRequest`

Файл: `services/media_broker/src/rpg_media_broker/models.py` — уже частично реализован.

Требования (зафиксировать как контракт, не ломая существующий код):

```python
MediaJobType = Literal["tts", "stt", "image", "avatar"]

class MediaJobRequest(BaseModel):
    """Incoming request to create media job."""

    model_config = ConfigDict(populate_by_name=True)

    job_type: MediaJobType = Field(..., alias="jobType")
    payload: dict[str, Any] = Field(...)
    client_token: str | None = Field(
        default=None,
        alias="clientToken",
        description="Idempotency token supplied by client.",
    )
````

Особенности:

* `jobType` — основной индикатор пайплайна: `tts` | `image` (MVP) + уже предусмотренные `stt`/`avatar`.
* `payload` — свободная структура, но для TTS/IMG подразумевается:

  * TTS: `{"text": str, "voice": str?, "speed": float?, "model": str?}`.
  * IMG: `{"prompt": str, "style": str?, "seed": int?, "width": int?, "height": int?, "model": str?, "postproc": str?}`.
* `clientToken` — идемпотентность на стороне клиента (комбинатор с кешем по хэшу).

### 2.2.2. `MediaJobRecord` и `MediaJobResponse`

`MediaJobRecord` — внутренний формат:

```python
class MediaJobRecord(BaseModel):
    """Internal representation of media job."""

    job_id: str = Field(..., alias="jobId")
    job_type: MediaJobType = Field(..., alias="jobType")
    payload: dict[str, Any]
    status: MediaJobStatus                             # queued|processing|succeeded|failed
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        alias="createdAt",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        alias="updatedAt",
    )
    client_token: str | None = Field(default=None, alias="clientToken")

    model_config = ConfigDict(populate_by_name=True)
```

`MediaJobResponse` — формат наружу (зеркалит `MediaJobRecord`):

```python
class MediaJobResponse(BaseModel):
    """Response returned to client for GET/POST requests."""

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(..., alias="jobId")
    job_type: MediaJobType = Field(..., alias="jobType")
    status: MediaJobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    client_token: str | None = Field(default=None, alias="clientToken")

    @classmethod
    def from_record(cls, record: MediaJobRecord) -> "MediaJobResponse":
        return cls.model_validate(record.model_dump(by_alias=True))
```

ТЗ: эти модели считаем **каноническим контрактом** для `/v1/media/jobs` и не ломаем их при доработке.

## 2.3. API-слой (routes)

Файл: `services/media_broker/src/rpg_media_broker/api/routes.py` — уже реализован базовый контракт:

* `GET /health` → `HealthPayload(status="ok", api_version=settings.api_version)`;
* `POST /v1/media/jobs`:

  * принимает `MediaJobRequest`;
  * `202 Accepted`;
  * `response_model=MediaJobResponse`;
  * оборачивается `rate_limit` (опциональный токен-бакет);
* `GET /v1/media/jobs/{job_id}`:

  * возвращает `MediaJobResponse`;
  * `404`, если job не найдена.

ТЗ:

* Поведение оставить, как есть.
* Гарантировать:

  * POST всегда возвращает `status="queued"` или `"succeeded"` (если job уже готова/кеширована);
  * GET возвращает актуальные `status`, `result`, `error` из `MediaJobRecord`.

## 2.4. MediaJobManager: жизненный цикл и кеш по хэшу

Файл: `services/media_broker/src/rpg_media_broker/manager.py`.

### 2.4.1. Текущая структура (уже есть)

* In-memory структуры:

  ```python
  self._jobs: OrderedDict[str, MediaJobRecord]
  self._jobs_by_token: Dict[str, str]
  self._queue: asyncio.Queue[str]
  self._workers: list[asyncio.Task[None]]
  self._shutdown: asyncio.Event
  self._lock: asyncio.Lock
  ```

* Методы:

  * `start()/stop()` — запуск/остановка воркеров;
  * `enqueue()` — постановка в очередь + идемпотентность по `clientToken`;
  * `get_job()`, `as_response()` — доступ к job;
  * `_worker_loop()` → `_process_job(job_id)` → `_build_result(record)` → `_trim_history_locked()`.

* Stub-результаты:

  * **TTS**:

    ```python
    text = record.payload.get("text", "")
    duration_ms = max(400, len(text) * 40)
    return {
        "audioUrl": f"https://cdn.rpg/audio/{record.job_id}.ogg",
        "durationMs": duration_ms,
        "voice": record.payload.get("voice", "default"),
    }
    ```

  * **IMG**:

    ```python
    style = record.payload.get("style", "concept")
    return {
        "cdnUrl": f"https://cdn.rpg/images/{record.job_id}.webp",
        "style": style,
        "width": record.payload.get("width", 1024),
        "height": record.payload.get("height", 1024),
    }
    ```

### 2.4.2. Расширение: кеш по контент-хэшу

Добавить в `MediaJobManager`:

```python
self._jobs_by_hash: Dict[str, str] = {}
```

Где `hash` — **контент-хэш** по описанию из Главы 5:

* Для TTS:

  ```text
  key = hash(text + voice + speed + model)
  ```

* Для IMG:

  ```text
  key = hash(prompt + style + seed + size + model + postproc)
  ```

Реализация:

1. Вынести утилиту:

   ```python
   import hashlib, json

   def _job_hash(job_type: MediaJobType, payload: dict[str, Any]) -> str:
       if job_type == "tts":
           key = {
               "jobType": "tts",
               "text": payload.get("text", ""),
               "voice": payload.get("voice", "default"),
               "speed": payload.get("speed", 1.0),
               "model": payload.get("model", "default"),
           }
       elif job_type == "image":
           key = {
               "jobType": "image",
               "prompt": payload.get("prompt", ""),
               "style": payload.get("style", "concept"),
               "seed": payload.get("seed", 0),
               "width": payload.get("width", 1024),
               "height": payload.get("height", 1024),
               "model": payload.get("model", "default"),
               "postproc": payload.get("postproc", "none"),
           }
       else:
           # для статика/stt/avatar пока можно не кешировать
           return ""

       raw = json.dumps(key, sort_keys=True, separators=(",", ":")).encode("utf-8")
       return hashlib.sha256(raw).hexdigest()
   ```

2. Логика в `enqueue()`:

   ```python
   async def enqueue(self, request: MediaJobRequest) -> MediaJobRecord:
       async with self._lock:
           # 1. Идемпотентность по clientToken (как сейчас)
           if request.client_token:
               existing_id = self._jobs_by_token.get(request.client_token)
               if existing_id:
                   logger.debug("Returning existing job for token %s", request.client_token)
                   return self._jobs[existing_id]

           # 2. Кеш по контент-хэшу (для tts/image)
           job_hash = _job_hash(request.job_type, request.payload)
           if job_hash:
               existing_id = self._jobs_by_hash.get(job_hash)
               if existing_id:
                   logger.debug("Cache hit for media hash %s", job_hash)
                   return self._jobs[existing_id]

           # 3. Создание новой job
           job_id = uuid4().hex
           record = MediaJobRecord(
               jobId=job_id,                            # type: ignore[arg-type]
               jobType=request.job_type,
               payload=request.payload,
               status="queued",
               clientToken=request.client_token,
           )
           self._jobs[job_id] = record
           if request.client_token:
               self._jobs_by_token[request.client_token] = job_id
           if job_hash:
               self._jobs_by_hash[job_hash] = job_id

           self._trim_history_locked()

       await self._queue.put(job_id)
       return record
   ```

3. В `_trim_history_locked()` при удалении job:

   * очищать и `self._jobs_by_hash` (по найденному job_id).

Таким образом:

* **clientToken** даёт идемпотентность «по клиенту» (обновление UI без дубликатов);
* **контент-хэш** даёт кеш на уровне сервиса (одинаковый запрос от разных клиентов не создаёт лишних jobs, если есть живой результат в памяти).

TTL пока реализуется грубо через `job_history_limit` (ограничение истории). На прод-слое можно будет добавлять явный TTL или переносить в Redis/PostgreSQL.

## 2.5. Настройки и rate-limit

Файл: `config.py` уже содержит:

* `api_version: str`;
* `worker_concurrency: int` (1..8);
* `processing_delay_ms: int` — искусственная задержка для детерминированных тестов;
* `job_history_limit: int` — ограничение in-memory истории;
* `rate_limit_enabled: bool`, `rate_limit_rps: float`, `rate_limit_burst: int`.

ТЗ:

* **Не менять** семантику существующих полей.
* Для локальной разработки:

  * по умолчанию `rate_limit_enabled=False`;
  * `processing_delay_ms` может быть >0, чтобы тесты/демо не «мелькали» мгновенно.
* Для stage/prod (дальше по проекту) эти параметры будут подняты через окружение.

## 2.6. Минимальные тесты (без фанатизма по покрытию)

Расширять `services/media_broker/tests/test_media_broker.py` **точечно**:

1. Уже есть тест на идемпотентность по `clientToken` — сохранить.

2. Добавить **один** тест на кеш по контент-хэшу без `clientToken`:

   * Запуск `create_app()`, TestClient;
   * Два POST запроса с одинаковым `jobType="tts"` и одинаковым `payload`, но **без `clientToken`**;
   * Проверить:

     * оба ответа 202;
     * `jobId` совпадает.

3. Smoke-тест на `GET /v1/media/jobs/{job_id}`:

   * создать job (POST);
   * сразу сделать GET (job может быть `queued` или `succeeded` в зависимости от `processing_delay_ms`);
   * убедиться, что формат ответа совпадает с `MediaJobResponse` (наличие `jobId`, `jobType`, `status`, `createdAt`, `updatedAt`).

Никаких дополнительных нагрузочных/интеграционных тестов в этом ТЗ **не требуем**.

---

# 3. Лёгкий observability-слой

## 3.1. Принципы

* **Единый подход для всех сервисов**: `gateway_api`, `party_sync`, `media_broker` используют одну и ту же схему:

  * `setup_observability(app, service_name=...)` в `app.create_app`;
  * Middleware `inject_trace_id` + `http_logger` в самом приложении;
  * `observability/logging.json` + stdout JSON-логи.
* **Фича-флаги через окружение**:

  * `ENABLE_OTEL=true` → включить OpenTelemetry-трейсинг (OTLP HTTP → `OTEL_EXPORTER_OTLP_ENDPOINT`);
  * `ENABLE_METRICS=true` → включить `/metrics` (prometheus-fastapi-instrumentator).
* **Никакой тяжёлой магии**:

  * если OTel/Prometheus не настроены → сервисы продолжают работать;
  * любые ошибки при инициализации телеметрии проглатываются (логируются максимум на debug).

## 3.2. Структура кода

Артефакты уже существуют:

* `observability/logging.json` — JSON-логгер с полем `trace_id`;
* `observability/prometheus/rules/app-rules.yaml` — пример алертов (latency, error-rate, queue depth и т.д.);
* `observability/trace-context.md` — текстовое описание trace-контекста;
* по сервисам:

  * `services/gateway_api/src/rpg_gateway_api/observability.py`;
  * `services/party_sync/src/rpg_party_sync/observability.py`;
  * `services/media_broker/src/rpg_media_broker/observability.py`.

ТЗ: эти файлы считаются **единственным местом настройки трейсинга/метрик** в каждом сервисе. Остальные части кода должны только вызывать `setup_observability`.

## 3.3. Трейсинг (OpenTelemetry)

Во всех трёх `observability.py`:

```python
def setup_observability(app: FastAPI, *, service_name: str) -> None:
    try:
        if os.environ.get("ENABLE_OTEL", "false").lower() in {"1", "true", "yes"}:
            _enable_tracing(service_name)
    except Exception:
        pass
    try:
        if os.environ.get("ENABLE_METRICS", "false").lower() in {"1", "true", "yes"}:
            _enable_metrics(app)
    except Exception:
        pass
```

`_enable_tracing`:

* импортирует:

  * `opentelemetry.trace`;
  * `OTLPSpanExporter` (HTTP/OTLP);
  * `FastAPIInstrumentor`;
  * `RequestsInstrumentor`;
  * `TracerProvider`, `BatchSpanProcessor`;
* использует `OTEL_EXPORTER_OTLP_ENDPOINT` (по умолчанию `http://localhost:4318`);
* создаёт `Resource(service.name=service_name)`;
* вешает `BatchSpanProcessor(exporter)` на провайдера;
* вызывает:

  ```python
  FastAPIInstrumentor.instrument()
  RequestsInstrumentor().instrument()
  ```

ТЗ:

* Проверить, что во всех трёх сервисах `setup_observability(...)` вызывается **один раз** в `create_app` / фабрике приложения **до** регистрации маршрутов (как уже сделано в `media_broker.app` и `party_sync.app`, `gateway_api.app`).
* Дополнительно стандартизировать `service_name`:

  * `"gateway-api"`;
  * `"party-sync"`;
  * `"media-broker"`.

## 3.4. Метрики (Prometheus)

`_enable_metrics(app: FastAPI)`:

* импортирует `prometheus_fastapi_instrumentator.Instrumentator`;
* выполняет:

  ```python
  Instrumentator().instrument(app).expose(app)
  ```

Что даёт:

* `/metrics` endpoint на том же FastAPI;
* стандартные HTTP-метрики (latency, rps, error rate).

Уже достаточно для локального и dev/stage окружения. Дальнейшие бизнес-метрики (queue depth, cache-hit, DLQ) будут добавляться позже в соответствующих местах (например, в `MediaJobManager`).

## 3.5. Логи и корреляция

### 3.5.1. Конфиг логгера

`observability/logging.json`:

* формат `"pythonjsonlogger.jsonlogger.JsonFormatter"`;
* форматирование: `%(asctime)s %(name)s %(levelname)s %(message)s %(trace_id)s`;
* root-логгер уровня INFO.

Каждый сервис:

* в своём `app.py` реализует `_setup_logging()`:

  ```python
  config_path = Path.cwd() / "observability" / "logging.json"
  if config_path.exists():
      with config_path.open("r", encoding="utf-8") as fh:
          cfg = json.load(fh)
      logging.config.dictConfig(cfg)
  ```

* вызывает `_setup_logging()` в lifespan/middleware, до старта сервиса.

ТЗ:

* окончательно зафиксировать паттерн `_setup_logging()` как **канонический** для всех сервисов (он уже одинаковый в gateway_api, party_sync, media_broker — не менять).

### 3.5.2. trace_id в логах и ответах

Во всех сервисах уже есть middleware `inject_trace_id`:

* читает `x-trace-id` / `x-request-id` из входящего запроса;
* если нет — генерирует `uuid4().hex`;
* пишет `request.state.trace_id`;
* добавляет в ответ заголовки:

  * `X-Trace-Id`;
  * `X-Request-Id` (если ещё не установлен).

Дополнительно есть `http_logger`:

* меряет `elapsedMs` per запрос;
* логирует строку вида:

  ```text
  method=GET path=/v1/... status=200 elapsedMs=15 traceId=<...>
  ```

ТЗ:

* Сохранить этот паттерн в трёх сервисах без изменений;
* Гарантировать, что во всех бизнес-логах, где возможно, traceId пробрасывается либо:

  * через `request.state.trace_id`, либо
  * через OTel-корреляцию (resource/span);
* Для ошибок (HTTP 4xx/5xx) JSON-ответы содержат поле `"traceId"` (как уже реализовано в gateway_api и party_sync; media_broker — только в `/config`, это достаточно для MVP).

## 3.6. Минимальные проверки

Без расширенного тест-покрытия, только smoke:

1. Локально, для каждого сервиса:

   * без `ENABLE_OTEL/ENABLE_METRICS`:

     * сервис стартует;
     * `/metrics` недоступен или пуст (поведение зависит от Instrumentator, но нам ОК).
   * с `ENABLE_METRICS=true`:

     * `/metrics` отвечает 200;
     * присутствуют http-метрики.
   * с `ENABLE_OTEL=true` + локальный OTLP-коллектор:

     * в коллектор начинают поступать трейсы.

2. Проверка JSON-логов (ручная):

   * запуск `uvicorn ... --log-config observability/logging.json`;
   * один запрос к `/health` и к любому основному эндпоинту;
   * убедиться, что в stdout появляются JSON-строки с полем `trace_id`.

---

# 4. План работ для Codex (пошагово)

## 4.1. Media-broker

1. `manager.py`:

   * добавить `self._jobs_by_hash: Dict[str, str] = {}` в `__init__`;
   * реализовать `_job_hash(job_type, payload)` по формуле контент-хэшей из Главы 5;
   * расширить `enqueue()`:

     * сначала проверка `clientToken`;
     * затем — кеш по контент-хэшу (для `tts`/`image`);
     * при создании job — запись в `_jobs_by_hash`;
   * расширить `_trim_history_locked()`, чтобы чистить `_jobs_by_token` и `_jobs_by_hash`.

2. Минимальное расширение теста `test_media_broker.py`:

   * тест на кеш по хэшу без `clientToken`.

3. Прогнать `pytest services/media_broker`.

## 4.2. Observability

1. Проверить, что во всех трёх сервисах:

   * `setup_observability(app, service_name="...")` вызывается в `create_app` **один раз**;
   * `_setup_logging()` использует `observability/logging.json`.

2. Для локальной отладки добавить в README/документацию (опционально):

   * пример запуска с `ENABLE_OTEL` и `ENABLE_METRICS`.

---

# 5. Definition of Done

1. `Media-broker`:

   * `POST /v1/media/jobs`:

     * возвращает `202` + `MediaJobResponse`;
     * при повторном запросе **с тем же `clientToken`** → тот же `jobId`;
     * при повторном запросе **с тем же контентом TTS/IMG, но без `clientToken`** → тот же `jobId` (пока job есть в in-memory истории).
   * `GET /v1/media/jobs/{job_id}` возвращает корректное состояние job.
   * Stub-результаты для TTS/IMG возвращают валидные структуры (`audioUrl`, `durationMs`, `cdnUrl`, `width/height`, и т.п.).

2. Observability:

   * Все три сервиса:

     * умеют запускаться с/без `ENABLE_OTEL` и `ENABLE_METRICS`;
     * логируют запросы в JSON-формате с `trace_id`;
     * отдают `X-Trace-Id` и `X-Request-Id` в ответах.
   * При включённой метрике `/metrics` отдаёт базовые http-метрики.

3. Тесты:

   * `pytest services/media_broker` зелёный;
   * никаких новых тяжёлых тестов или нагрузочных сценариев в этом ТЗ не требуется.

```markdown
```
