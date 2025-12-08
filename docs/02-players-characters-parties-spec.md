# RPG-Bot — Игроки, персонажи, партии  
## 02. Players / Characters / Parties / Chronicles (L2)

## 1. Цель

Определить стабильную модель:

- **игрока** (Player, привязанный к Telegram),
- **персонажа** (Character),
- **партии** (Party),
- **летописи свершений** (L2: Chronicles),

и интегрировать её с Campaign Engine и существующей авторизацией.

## 2. Игрок (Player)

### 2.1. Модель

- `Player`:
  - `id`
  - `telegram_id`
  - `display_name`
  - `created_at`
  - `last_login_at`
  - `settings` (jsonb: язык, предпочтения и т.п.)

**Инварианты:**

- `telegram_id` уникален.
- Один Telegram-аккаунт → один Player.

### 2.2. Авторизация

- Авторизация уже реализована через `/v1/auth/telegram`.  
- Необходимо:
  - обеспечить жёсткую привязку токена к `player_id`;
  - в `gateway_api` иметь удобный способ получания текущего `Player`.

## 3. Персонаж (Character)

### 3.1. Модель

- `Character`:
  - `id`
  - `player_id`
  - `name`
  - `archetype` / `class` (по дизайн-решениям игры)
  - `race` (если используется)
  - `level`
  - `xp`
  - `core_stats` (jsonb: сила, ловкость, интеллект и т.п.)
  - `skills` (jsonb: список с ранками)
  - `inventory_ref` (ссылка на инвентарь)
  - `status` (`ACTIVE`, `RETIRED`, `DEAD`, `OBSOLETE`)
  - `created_at`, `updated_at`

### 3.2. Ограничения

- Один Player может иметь несколько персонажей.
- Для OBT достаточно:
  - 3–5 активных персонажей на одного игрока.

### 3.3. Связь с кампаниями

- Таблица `character_campaign_runs`:
  - `character_id`
  - `campaign_run_id`
  - `role` (`MAIN`, `GUEST`, `NPC_CONTROLLED`)

## 4. Партия (Party)

### 4.1. Модель

- `Party`:
  - `id`
  - `name` (опционально)
  - `leader_character_id`
  - `created_at`

- `PartyMember`:
  - `party_id`
  - `character_id`
  - `role` (`LEADER`, `MEMBER`, `SPECTATOR`)
  - `joined_at`
  - `left_at` (nullable)

### 4.2. Связь с кампанией

- У каждой `CampaignRun` есть `party_id`.
- У партии может быть:
  - **активный** `campaign_run_id` (текущий run),
  - история предыдущих run’ов.

## 5. Летописи (L2: Chronicles)

### 5.1. Сырые события

- `CharacterEvent`:
  - `id`
  - `character_id` (или `party_id`, если событие групповое)
  - `campaign_run_id`
  - `world_event_type` (enum: `KILL_NPC`, `SPARE_NPC`, `SAVE_CITY`, `BETRAYAL`, `QUEST_SUCCESS`, `QUEST_FAIL`, др.)
  - `importance` (`MICRO`, `MESO`, `MACRO`)
  - `payload` (jsonb: дополнительные детали)
  - `timestamp`

Хранится как **immutable** лог.

### 5.2. Использование

- Campaign Engine пишет `CharacterEvent` по результатам значимых решений/исходов.
- Retcon Engine читает их (через RetconPackage в Wave OBT-2).
- Для Adventure Summary строится человекочитаемое резюме из `CharacterEvent`.

## 6. API

### 6.1. Профиль игрока и персонажи

- `GET /v1/me`
  - возвращает профиль Player + краткие данные по персонажам.

- `GET /v1/characters`
  - список персонажей игрока.

- `POST /v1/characters`
  - создание персонажа (минимальный билд: имя + архетип).

- `PATCH /v1/characters/{id}`
  - обновление части полей (косметика, настройки).

- `DELETE /v1/characters/{id}` или `POST /v1/characters/{id}/retire`
  - вывод персонажа из активного пула (статус `RETIRED`).

### 6.2. Партии

- `GET /v1/parties`
  - список партий, где есть персонажи игрока.

- `POST /v1/parties`
  - создание партии (лидер — указанный character_id).

- `POST /v1/parties/{id}/join`
  - присоединение персонажа к партии.

- `POST /v1/parties/{id}/leave`
  - выход персонажа из партии.

## 7. Definition of Done

- Реализованы таблицы `players`, `characters`, `parties`, `party_members`, `character_campaign_runs`, `character_events`.  
- gateway_api предоставляет программы/функции для получения `Player` и активных персонажей по токену.  
- Реализованы описанные endpoint’ы с basic-валидацией и авторизацией.  
- Campaign Engine обновляет статы персонажей и пишет `CharacterEvent` по результатам сцен.  
- Написаны тесты:
  - создание персонажа → создание партии → запуск CampaignRun → запись событий в летопись.
