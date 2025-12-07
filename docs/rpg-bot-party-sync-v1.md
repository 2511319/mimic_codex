# ТЗ (Dev) — Party Sync v1: протокол и сервис синхронизации кампаний

Документ предназначен для реализации и доводки сервиса `Party Sync` в репозитории `mimic_codex-main` (папка `services/party_sync`) силами Codex/разработчика. Формат — техническое ТЗ под конкретный код: какие файлы правим, какое поведение нужно получить, как проверяем.

---

## 1. Цель и контекст

**Цель блока:**
Сделать из `services/party_sync` **полноценный, стабильный WebSocket-хаб синхронизации кампаний**, к которому может безопасно подключаться UI (Telegram Mini App / dev-панель) и:

* получать актуальные события по выбранной кампании;
* отправлять события в кампанию;
* при позднем подключении — получать релевантную историю (replay) без дыр и рассинхрона.

Сервис **НЕ** отвечает за бизнес-логику игры (боёвка, расчёт урона, нарративная логика). Он обеспечивает:

* транспорт (WebSocket);
* маршрутизацию по `campaign_id`;
* хранение и реплей части истории;
* базовую защиту от спама (rate-limit **для REST-broadcast**, а не для WS на этом этапе).

---

## 2. Область работ

### 2.1. Что входит

1. **Доработка доменных моделей** (`services/party_sync/src/rpg_party_sync/models.py`):

   * `BroadcastMessage`
   * `BroadcastRequest`
   * `BroadcastAck`
   * `HistoryEntry`

2. **Реализация хаба и сессий** (`services/party_sync/src/rpg_party_sync/hub.py`):

   * хранение активных кампаний и подключений;
   * приём сообщений от WebSocket-клиентов;
   * широковещательная рассылка по кампании;
   * хранение ограниченной истории per-campaign;
   * реплей истории для поздних подписчиков.

3. **Маршруты API** (`services/party_sync/src/rpg_party_sync/api/routes.py`):

   * WebSocket-маршрут `/ws/campaign/{campaign_id}`;
   * REST-маршрут для broadcast’а в кампанию (по уже заложенной заготовке в файле);
   * корректная обработка ошибок (ValidationError, HTTPException) и закрытие WS.

4. **Интеграция с конфигом и rate limit**:

   * чтение `Settings` (history-limit, rate-limit для REST);
   * использование `rate_limit` как FastAPI-dependency для REST-broadcast.

5. **Интеграция с логированием и observability**:

   * логирование ключевых операций (подключение, отключение, broadcast, ошибки);
   * единый traceId для цепочек «REST broadcast → доставлено в WS».

6. **Приведение к зелёному состоянию тестов**:

   * `services/party_sync/tests/test_party_sync.py` должен проходить без модификации теста.

### 2.2. Что НЕ входит

* Авторизация WebSocket по JWT / ролям — пока **не реализуем**, но код не должен этому мешать (оставить точки расширения).
* Нарративная логика, обработка игровых действий — Party Sync работает с **абстрактными событиями** (`eventType`, `payload`), не интерпретируя их.
* Хранение истории в БД — v1 допускает in-memory реализацию, но код должен быть написан так, чтобы позже можно было вынести storage в отдельный слой.

---

## 3. Требования к протоколу WebSocket

### 3.1. URL и handshake

* WebSocket-endpoint:
  `GET /ws/campaign/{campaign_id}`

* При успешном подключении:

  * сервер регистрирует соединение (кампания + WebSocket);
  * **не обязан** сразу отправлять snapshot/handshake-сообщение (это можно добавить позже), но:

    * для теста требуется, чтобы при последующем подключении реплеился последний event.

### 3.2. Формат сообщений

**Сообщения от клиента к серверу** (в тестах уже используется):

```json
{
  "eventType": "timer_tick",
  "payload": {
    "secondsLeft": 20
  }
}
```

**Серверная модель `BroadcastMessage`:**

Pydantic-класс (ориентировочный состав полей):

* `event_type: str` — alias `eventType` (обязательное поле).
* `payload: dict[str, Any]` — произвольные данные события.
* `trace_id: str | None` — alias `traceId`, опционально:

  * если клиент не передал, можно проставить `None`;
  * если событие идёт через REST-broadcast, traceId берётся из контекста/заголовков.
* `sender_id: str | None` — alias `senderId`, опционально:

  * на данном этапе допустимо всегда `None`;
  * закладываем поле как extension-point под auth.

**Требование по сериализации:**

* `model_config = ConfigDict(populate_by_name=True)` уже заложен — нужно обеспечить корректную сериализацию в JSON:

  * при отправке на клиента сервер должен вернуть именно:

    ```json
    {
      "eventType": "...",
      "payload": { ... },
      "traceId": null,
      "senderId": null
    }
    ```
  * это видно из конца `test_party_sync.py`.

### 3.3. Поведение при входящем сообщении (WS)

Для любого активного `WebSocket` в кампании:

1. Сервер получает `json` от клиента.
2. Пытается валидировать в `BroadcastMessage`.

   * При `ValidationError` — соединение закрывается с кодом `1003` и reason `"Invalid payload"`
     (это уже частично описано в `routes.py`).
3. При успехе:

   * сообщение записывается в историю соответствующей кампании (см. историю ниже);
   * отправляется всем текущим подписчикам кампании (включая отправителя) в виде JSON, соответствующего `BroadcastMessage`.

### 3.4. Replay истории

Требуемое поведение, вытекающее из теста:

* A подключается к `/ws/campaign/cmp2`.
* A отправляет событие `{eventType: "timer_tick", payload: {"secondsLeft": 20}}`.
* A получает echo/бродкаст.
* Позже B подключается к `/ws/campaign/cmp2`.
* При подключении B **первым** сообщением получает replay:

```json
{
  "eventType": "timer_tick",
  "payload": {"secondsLeft": 20},
  "traceId": null,
  "senderId": null
}
```

Требования к реализации:

* История хранится per-campaign в структуре `deque[HistoryEntry]`.
* В v1 достаточно хранить **последние N событий**:

  * `N` брать из `Settings` (например, `history_limit` — если поле не задано, выбрать разумный дефолт ~100).
* При новом подключении:

  * пробежать по истории (по возрастанию времени/добавления) и отправить все events клиенту **до начала приёма новых сообщений** от него;
  * порядок гарантирован.

---

## 4. REST-broadcast API

В `api/routes.py` уже есть импорт `BroadcastRequest` и `BroadcastAck`. Требуется:

1. Реализовать REST-маршрут (название и path опираемся на уже заложенный в файле каркас — Codex должен его открыть и дочинить, **не придумывать новый URL**, а довести уже описанный).

2. Поведение REST-broadcast:

   * Вход: `BroadcastRequest`:

     * `campaign_id: str` (скорее всего alias `campaignId`).
     * `message: BroadcastMessage`.
   * Dependency `rate_limit` должен применяться (лимит на частоту broadcast’ов).
   * Логика:

     1. Вызвать `hub.broadcast(campaign_id, message)`.
     2. Получить количество доставок `delivered: int`.
     3. Вернуть `BroadcastAck`:

        * `accepted: bool` — `True`, если broadcast отработал без исключений;
        * `delivered: int` — количество получателей (может быть 0, если никто не подключён).

3. Ошибки:

   * При выбросе `HTTPException` из хаба — пробрасывать статус вверх.
   * При `ValidationError` — возвращать `422` с дефолтной схемой FastAPI.

---

## 5. Доменные модели (Pydantic)

Файл: `services/party_sync/src/rpg_party_sync/models.py`.

### 5.1. BroadcastMessage

Как описано выше:

* `event_type: str = Field(..., alias="eventType")`
* `payload: dict[str, Any]`
* `trace_id: str | None = Field(default=None, alias="traceId")`
* `sender_id: str | None = Field(default=None, alias="senderId")`
* `model_config = ConfigDict(populate_by_name=True)`

### 5.2. BroadcastRequest

Назначение: запрос для REST-маршрута broadcast.

Рекомендуемая структура:

* `campaign_id: str = Field(..., alias="campaignId")`
* `message: BroadcastMessage`

### 5.3. BroadcastAck

Уже частично описан:

* `accepted: bool = True`
* `delivered: int` (≥0)

Оставить как есть, дописав при необходимости описания.

### 5.4. HistoryEntry

Уже описан:

* `event: BroadcastMessage`
* `created_at: datetime = Field(default_factory=...)`

Важно: обеспечить, чтобы `created_at` всегда был в `UTC` (`timezone.utc` уже задействован).

---

## 6. Архитектура и внутренняя реализация

Файл: `services/party_sync/src/rpg_party_sync/hub.py`.

### 6.1. Структура классов

Рекомендуемая структура (ориентируется на уже существующую заготовку):

1. `class PartySession:`

   * Инкапсулирует состояние для **одной кампании**:

     * набор активных WebSocket-подключений: `Set[WebSocket]`;
     * история событий: `deque[HistoryEntry]`;
     * зависимость от `Settings` (лимиты истории).

   * Методы:

     * `__init__(self, settings: Settings)`.
     * `async connect(self, websocket: WebSocket) -> None`:

       * `await websocket.accept()`;
       * добавить в `connections`;
       * `await self._replay_history(websocket)`.
     * `async disconnect(self, websocket: WebSocket) -> None`:

       * убрать из `connections` без исключений.
     * `async broadcast(self, message: BroadcastMessage, *, include_sender: bool) -> int`:

       * добавить `HistoryEntry` в `deque` с учётом лимита;
       * отправить `message.model_dump(by_alias=True)` всем подключенным:

         * если `include_sender=True` — отправлять всем,
         * иначе — всем, кроме одного WebSocket’а (передавать ссылку на sender при необходимости).
       * вернуть количество успешно отправленных.
     * `async _replay_history(self, websocket: WebSocket) -> None`:

       * по очереди отправить все `entry.event` в JSON.

2. `class PartyHub:`

   * Управляет множеством `PartySession` по `campaign_id`:

     * `self._sessions: Dict[str, PartySession]`;
     * `self._lock: asyncio.Lock` для конкурентного доступа.

   * Методы:

     * `__init__(self, settings: Settings)`.
     * `async acquire_session(self, campaign_id: str) -> PartySession`:

       * под `self._lock` возвращает существующую или создаёт новую сессию.
     * `async handle_connection(self, campaign_id: str, websocket: WebSocket) -> None`:

       * получает `session = await self.acquire_session(campaign_id)`;
       * вызывает `await session.connect(websocket)`;
       * в цикле `while True`:

         * `data = await websocket.receive_json()`;
         * `message = BroadcastMessage.model_validate(data)`;
         * `await session.broadcast(message, include_sender=True)`.
       * ловит `WebSocketDisconnect`:

         * вызывает `await session.disconnect(websocket)`;
         * если после этого у сессии нет подключений, можно удалить `campaign_id` из `_sessions`.
     * `async broadcast(self, campaign_id: str, message: BroadcastMessage) -> int`:

       * уже частично реализован в файле (виден хвост) — дописать недостающую часть/обвязку.

### 6.2. Поток выполнения для WS

1. FastAPI-маршрут `/ws/campaign/{campaign_id}` принимает `WebSocket`, передаёт в `hub.handle_connection`.
2. `handle_connection`:

   * подключает сокет;
   * реплеит историю;
   * далее в цикле читает входящие, валидирует → бродкастит.
3. Ошибки:

   * `WebSocketDisconnect` — нормальное завершение;
   * `ValidationError` — закрытие кодом `1003` (это уже реализовано в `routes.py`);
   * любые другие — лог + `websocket.close(code=1011, reason="Internal error")`.

---

## 7. Конфигурация (Settings)

Файл: `services/party_sync/src/rpg_party_sync/config.py`.

Внутри уже есть `Settings(BaseSettings)` и `HealthPayload`.
Нужно:

1. Добавить поля (если их ещё нет):

   * `history_limit: int = Field(100, ge=0, description="Max number of events to keep in memory per campaign")`
   * `max_campaigns: int = Field(1000, ge=1, description="Max number of campaigns to track in memory")`
   * Параметры rate limit, которые уже используются в `rate_limit.py`:

     * `rate_limit_rps: float = 5.0`
     * `rate_limit_burst: float = 10.0`

2. Убедиться, что значения читаются из `.env`, но имеют адекватные дефолты.

3. В `HealthPayload` отразить хотя бы:

   * `status: Literal["ok"]`
   * `api_version: str`

(Сами детали health уже частично реализованы в `routes.py`.)

---

## 8. Логирование и observability

### 8.1. Требования

* Использовать стандартный `logging.getLogger(__name__)`.
* Логировать:

  * подключение/отключение WS (debug/info);
  * broadcast: `event_type`, `campaign_id`, `delivered`;
  * ошибки в `handle_connection` (warning/error).

### 8.2. TraceId

* В scope v1 достаточно:

  * если в `BroadcastMessage.trace_id` есть значение — логировать его вместе с событием;
  * если нет — можно не генерировать (генерация traceId может быть добавлена в дальнейшем через middleware).

---

## 9. Нефункциональные требования

* **Порядок доставки:** внутри одной `campaign_id` события должны доходить до подключенных клиентов **в том же порядке**, в котором они были приняты сервером.
* **Производительность:** v1 не оптимизируем агрессивно; главное — корректность и отсутствие гонок.
* **Память:** за счёт `history_limit` нельзя допустить бесконтрольного роста памяти per-campaign.
* **Безопасность:** не выполнять `eval`/`exec`, не доверять `payload`, не ломать общий logging config.

---

## 10. Задачи для Codex (пошагово)

Эти шаги — то, что Codex должен сделать в репозитории `mimic_codex-main`.

### 10.1. `models.py`

1. Открыть `services/party_sync/src/rpg_party_sync/models.py`.
2. Дописать `BroadcastMessage`:

   * полный набор полей (eventType, payload, traceId, senderId);
   * алиасы и `model_config`.
3. Реализовать `BroadcastRequest` (структура по п.5.2).
4. Проверить/уточнить `BroadcastAck`, `HistoryEntry`; при необходимости добавить докстринги и описания.

### 10.2. `hub.py`

1. Открыть `services/party_sync/src/rpg_party_sync/hub.py`.
2. Реализовать:

   * класс, инкапсулирующий кампанию (Session/PartySession);
   * хранение подключений и истории;
   * методы `connect`, `disconnect`, `broadcast`, `_replay_history`.
3. В `PartyHub`:

   * реализовать `__init__` с хранением `Settings`;
   * реализовать `acquire_session` и, при необходимости, удаление пустых кампаний;
   * реализовать `handle_connection` по описанному флоу;
   * убедиться, что уже существующий `broadcast()` работает через `session.broadcast()` и логирует нужные поля.

### 10.3. `api/routes.py`

1. Открыть `services/party_sync/src/rpg_party_sync/api/routes.py`.
2. Найти REST-endpoint для broadcast (где используется `BroadcastRequest`, `BroadcastAck`, `rate_limit`).
3. Дочинить реализацию:

   * чтение `BroadcastRequest` из body;
   * вызов `hub.broadcast`;
   * возврат `BroadcastAck`.
4. Убедиться, что WebSocket-маршрут `/ws/campaign/{campaign_id}`:

   * вызывает `hub.handle_connection`;
   * корректно обрабатывает `ValidationError` и `HTTPException` (частично уже реализовано).

### 10.4. `config.py`

1. Открыть `services/party_sync/src/rpg_party_sync/config.py`.
2. Добавить/проверить поля конфигурации (history_limit, rate_limit_rps, rate_limit_burst, max_campaigns).
3. Убедиться, что `get_settings()` кешируется и используется в `hub.py` и `routes.py`.

### 10.5. Проверка

1. Локально выполнить:

   ```bash
   poetry run pytest services/party_sync/tests/test_party_sync.py
   ```
2. При необходимости прогнать весь Python-джоб:

   ```bash
   poetry run pytest
   ```

---

## 11. Ручные сценарии проверки (smoke для dev)

После того как Codex внесёт изменения, имеет смысл руками проверить (через `TestClient` или реальный сервер):

1. **Basic WS broadcast:**

   * Подключить два клиента к `/ws/campaign/cmp1`.
   * Отправить событие с одного клиента.
   * Убедиться, что оба получили идентичный JSON (с `traceId`, `senderId` = null).

2. **Replay:**

   * Подключить A → отправить событие.
   * Отключиться/оставить A.
   * Подключить B → сразу после подключения получить replay последнего события.

3. **REST broadcast:**

   * Вызвать REST-endpoint broadcast (тот, что реализован в `routes.py`) с JSON в формате `BroadcastRequest`.
   * Подключенный к соответствующей кампании WS-клиент должен получить событие.
   * В ответе REST должно быть `{"accepted": true, "delivered": <N>}`.

4. **Rate limit:**

   * Несколько раз подряд вызвать REST-broadcast с высоким RPS.
   * При превышении лимита получить `429` от `rate_limit`.

---

На выходе по этому ТЗ должен получиться **завершённый Party Sync v1**, который:

* умеет работать как WS-хаб на кампанию;
* поддерживает broadcast и replay;
* интегрирован с конфигом и rate-лимитом;
* проходит существующие тесты и готов к интеграции с внешним UI.
