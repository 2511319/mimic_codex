# RPG-Bot — Движок кампаний  
## 01. Campaign Engine & L1 Simulation

## 1. Цель

Определить и реализовать **движок кампаний** (Campaign Engine), который:

- управляет L1-слоем (Campaign Simulation) для конкретного приключения/run’а;
- оркестрирует сцены, проверки, бои и социальные эпизоды;
- интегрируется с Memory37/Genlayers для генеративных элементов;
- формирует итоги приключения (`AdventureSummary`) и `RetconPackage` для Retcon Engine.

## 2. Область ответственности Campaign Engine

Campaign Engine отвечает за:

- создание/инициализацию `CampaignRun` по шаблону кампании;
- состояние кампании (эпизоды, сцены, флаги, прогресс);
- обработку действий игроков (choices, skill-checks, combat actions);
- вызовы генеративных профилей (Scene/Combat/Social/Epilogue) **через** Genlayers;
- формирование структурированного результата приключения:
  - для игроков (Adventure Summary),
  - для мира (RetconPackage).

Не отвечает за:

- авторизацию (делает `gateway_api`);
- party-sync (делает `party_sync`, но Campaign Engine предоставляет хуки);
- TTS (отложено за рамки OBT).

## 3. Модель данных L1 (Campaign Simulation)

### 3.1. Базовые сущности

- `CampaignTemplate`  
  - `id`  
  - `world_id`  
  - `title`  
  - `description`  
  - `season_version` (например, `S1-v0.1`)  
  - ссылки на контент: основные эпизоды, ключевые NPC, локации.

- `CampaignRun`  
  - `id`  
  - `campaign_template_id`  
  - `party_id`  
  - `status` (`INIT`, `IN_PROGRESS`, `COMPLETED`, `ABORTED`)  
  - `current_episode_id`  
  - `current_scene_id`  
  - `created_at`, `finished_at`  
  - версия канона/контента на старте.

- `Episode`  
  - `id`  
  - `campaign_template_id`  
  - `order` / `graph_position`  
  - `type` (main / side / optional)  
  - входные/выходные условия (флаги, предыдущие сцены).

- `SceneState`  
  - `id`  
  - `campaign_run_id`  
  - `episode_id`  
  - `scene_type` (`story`, `combat`, `social`, `epilogue`)  
  - `profile` (генеративный профиль)  
  - `input_context_ref` (ссылки на лор/Memory37/предыдущие сцены)  
  - `generated_payload` (JSON, соответствующий профилю)  
  - `resolved` (bool)  
  - `result_flags` (итоги, флаги для дальнейшей логики).

- `FlagState`  
  - `id`  
  - `campaign_run_id`  
  - `key` (строка)  
  - `value` (bool/int/string/json)  
  - `source_scene_id`.

### 3.2. Стейт-машина кампании

Упрощённая схема:

1. `INIT` → создание `CampaignRun`, выбор стартового `Episode`.
2. `LOAD_SCENE` → выбор следующего `SceneState`:
   - из заранее описанного сценарного графа (content-пак),
   - либо генеративно (через Genlayers, на основе контекста).
3. `GENERATE_SCENE`:
   - Campaign Engine собирает контекст (`WorldView`, состояние L1, летописи L2) и вызывает Genlayers;
   - ответ валидируется JSON Schema соответствующего профиля.
4. `RESOLVE_PLAYER_ACTIONS`:
   - UI/party_sync присылают действия/выборы игроков;
   - выполняются проверки, броски, расчёты боёвки.
5. `APPLY_EFFECTS`:
   - обновление FlagState, SceneState, статы персонажей;
   - запись событий в L2 (летописи).
6. `NEXT_STEP`:
   - либо переход к следующей сцене/эпизоду,
   - либо завершение кампании → `COMPLETED`.

## 4. Интеграция с Memory37 и Genlayers

### 4.1. Сбор контекста

Для генеративного вызова Campaign Engine формирует `GenerationContext`:

- `world_id` / `campaign_template_id` / `campaign_run_id`;
- текущий `Episode` / `SceneState`;
- релевантные куски лора из Memory37:
  - world → region → city → location;
  - задействованные NPC/фракции;
- флаги L1 (состояние кампании, скрытые/видимые сюжеты);
- релевантные фрагменты летописей L2 для активной партии/персонажей;
- текущие отношения L3 (если уже реализованы).

### 4.2. Профили генерации

Для OBT используются уже заложенные профили:

- `scene` — narative сцена;
- `combat` — боевой эпизод (инициатива, цели, возможные действия);
- `social` — социальные интеракции, переговоры;
- `epilogue` — финальное резюме кампании.

Campaign Engine отвечает за:

- выбор профиля;
- формирование prompt-payload в формате Genlayers;
- валидацию ответа по JSON Schema.

## 5. Adventure Summary и RetconPackage

### 5.1. Adventure Summary (для игрока)

Структура (высокоуровневая):

- `campaign_run_id`
- `party_summary`:
  - участники, финальные статы, ключевые свершения;
- `timeline`:
  - краткое описание ключевых сцен/решений;
- `rewards`:
  - предметы, титулы, достижения;
- `world_local_effects`:
  - что изменилось в рамках **этой кампании** (NPC/локации/фракции).

### 5.2. RetconPackage (для Retcon Engine)

Минимальный состав:

- `world_id`
- `campaign_template_id`
- `campaign_run_id`
- `season_version`
- `world_deltas`:
  - изменения по NPC (per-run): жив/мертв/изгнан/изменил сторону;
  - изменения по фракциям/городам (усиление/ослабление, события);
- `player_impact`:
  - свершения партии/персонажей с типами действий (help/kill/betray/spare и т.д.);
- `meta_stats`:
  - распределение выборов по ключевым узлам сюжета.

Campaign Engine обязан:

- сформировать и сохранить `RetconPackage` при завершении run’а;
- отдать его:
  - в API (`/v1/campaign-runs/{id}/summary`),
  - в Retcon Engine (через отдельный внутренний вызов или очередь).

## 6. API (через gateway_api)

Основные endpoint’ы, которые должен реализовать/расширить gateway_api:

- `GET  /v1/campaigns`  
  — список доступных шаблонов кампаний.

- `POST /v1/campaign-runs`  
  body: `{ campaign_template_id, party_id }`  
  resp: `CampaignRun` + стартовое состояние.

- `GET  /v1/campaign-runs/{id}`  
  — текущее состояние кампании (эпизод, сцена, флаги).

- `POST /v1/campaign-runs/{id}/action`  
  — действие игрока/партии (выбор, каст скилла, боевое действие).  
  body: `PlayerAction`, resp: обновлённое состояние.

- `GET  /v1/campaign-runs/{id}/summary`  
  — возвращает `AdventureSummary` + вложенный/ссылочный `RetconPackage`.

## 7. Definition of Done (для Codex)

- Определены и реализованы модели L1 (CampaignRun, Episode, SceneState, FlagState).  
- Реализован Campaign Engine как слой/пакет, используемый gateway_api.  
- Реализованы описанные endpoint’ы в gateway_api.  
- Генеративные профили вызываются **через** Genlayers, ответы валидируются схемами.  
- При завершении run’а формируется и сохраняется `AdventureSummary` и `RetconPackage`.  
- Есть unit/интеграционные тесты базового сценария кампании (init → несколько сцен → эпилог).
