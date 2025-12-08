# RPG-Bot — Контракты Gateway ↔ UI  
## 07. API / WS Contracts for OBT UI

## 1. Цель

Зафиксировать набор REST/WS-контрактов, необходимых UI-команде для OBT-скоупа, и гарантировать их стабильность на период OBT.

## 2. OBT-скоуп UI-экранов

Минимальный набор:

1. **Экран входа / загрузки** — initData → авторизация → проверка здоровья сервиса.
2. **Экран выбора кампании** — список кампаний/шаблонов, создание run’а.
3. **Экран персонажей** — список, создание, выбор активного.
4. **Экран партии** — состав, статусы, присоединение к run’у.
5. **Основной экран сцены** — текст/структура сцены, варианты выбора, последствия.
6. **Боевой экран** — инициатива, цели, HP, действия.
7. **Экран инвентаря/лут-резюме** — полученные предметы/награды.
8. **Экран Adventure Summary** — итог run’а, свершения, что “мир запомнил”.

## 3. REST-контракты (gateway_api)

### 3.1. Health / Config

- `GET /v1/health`
- `GET /v1/config`
  - возвращает флаги и base-URL сервисов.

### 3.2. Auth / Player

- `POST /v1/auth/telegram`
  - уже реализован, нужен freeze контракта.

- `GET /v1/me`
  - профиль игрока + краткий список персонажей.

### 3.3. Characters / Parties

См. `02-players-characters-parties-spec.md`:

- `GET /v1/characters`
- `POST /v1/characters`
- `PATCH /v1/characters/{id}`
- `POST /v1/parties`
- `POST /v1/parties/{id}/join`
- `GET /v1/parties`

### 3.4. Campaigns / Runs

См. `01-campaign-engine-spec.md`:

- `GET /v1/campaigns`
- `POST /v1/campaign-runs`
- `GET /v1/campaign-runs/{id}`
- `POST /v1/campaign-runs/{id}/action`
- `GET /v1/campaign-runs/{id}/summary`

Важно:

- структура ответа `GET /v1/campaign-runs/{id}` должна быть:
  - достаточно богата, чтобы UI отрисовал состояние сцены/боя (SceneResponse/CombatResponse);
  - стабильна на период OBT.

### 3.5. Media

См. `06-media-layer-spec.md`:

- `GET /v1/media/jobs/{id}` — по необходимости для lazy-ген.

В большинстве случаев UI получает готовые `asset_url` напрямую в ответах Campaign Engine / в контенте.

## 4. WS-контракты (party_sync)

См. `05-realtime-and-party-sync-spec.md`.

UI должен:

- устанавливать WS-подключение к `party_sync` с токеном и параметрами (party_id / campaign_run_id / character_id);
- обрабатывать типы сообщений:
  - `system.hello`, `system.error`,
  - `party.join`, `party.leave`,
  - `action.request` (исходящие),
  - `action.result`, `scene.update`, `combat.update`, `vote.*` (входящие).

## 5. Стабильность контрактов

На период OBT:

- запрещены breaking-изменения без bump’а версии API.  
- Рекомендуется:

  - использовать явный префикс версий (`/v1/...`);
  - любые расширения делать **backward-compatible** (добавление полей, не меняя смысл существующих).

## 6. Документация

- OpenAPI-спека (`contracts/openapi/rpg-bot.yaml`) должна:
  - быть синхронизирована с реальным gateway_api;
  - использоваться UI-командой как источник правды.

## 7. Definition of Done

- Все описанные endpoint’ы реализованы и задокументированы в OpenAPI.  
- WS-протокол задокументирован (JSON Schema per type).  
- UI-команда подтверждает, что данные контрактов покрывают OBT-скоуп экранов.  
- Добавлены smoke-тесты:
  - сценарий “новый игрок → персонаж → партия → запуск кампании → несколько сцен → завершение → Adventure Summary”.
