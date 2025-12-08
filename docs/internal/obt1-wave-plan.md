# Wave OBT-1 — план внедрения (backend)

## Текущее состояние
- Gateway API: только auth (initData → JWT), knowledge/genlayers, нет моделей Player/Character/Party и Campaign Engine.
- Party Sync: простой WS-хаб без связки с Campaign Engine/партийными сущностями.
- Контракты/OpenAPI отражают только текущие эндпоинты генерации/здоровья.
- Хранилище/ORM отсутствуют; psycopg в зависимостях, но не используется.

## Архитектурные решения
- DB: PostgreSQL (psycopg) с fallback на in-memory для тестов/dev. Единый connection/provider в gateway_api.
- Модульные слои в gateway_api:
  - `data` (коннекторы + миграции on-start, SQL/CRUD-репозитории).
  - `domain` (модели/сервисы Players/Characters/Parties/Chronicles).
  - `campaign` (Campaign Engine L1, генерация сцен через Genlayers/Memory37).
  - `api` (FastAPI роуты, зависимости auth/current_player, schema-ответы).
- Данные кампаний: каталог `data/knowledge/campaigns/*.yaml` как source для `CampaignTemplate` (id/title/description/scenes graph).
- AdventureSummary/RetconPackage: хранение в таблицах `campaign_runs` и `adventure_summaries` (jsonb).

## Схема БД (Postgres)
- `players` (id serial/bigint, telegram_id bigint unique, display_name text, settings jsonb, created_at timestamptz, last_login_at timestamptz).
- `characters` (id bigserial, player_id fk, name text, archetype text, race text, level int, xp int, core_stats jsonb, skills jsonb, inventory_ref text, status text, created_at, updated_at).
- `parties` (id bigserial, name text, leader_character_id fk, active_campaign_run_id fk null, created_at).
- `party_members` (party_id fk, character_id fk, role text, joined_at, left_at null, pk(party_id, character_id)).
- `campaign_templates` (id text pk, world_id text, title text, description text, season_version text).
- `episodes` (id text pk, campaign_template_id fk, ord int, type text, metadata jsonb).
- `campaign_runs` (id uuid pk, campaign_template_id fk, party_id fk, status text, current_episode_id text, current_scene_id text, created_at, finished_at, canon_version text).
- `scene_states` (id uuid pk, campaign_run_id fk, episode_id text, scene_type text, profile text, input_context jsonb, generated_payload jsonb, resolved bool, result_flags jsonb, created_at, resolved_at).
- `flag_states` (id bigserial pk, campaign_run_id fk, key text, value jsonb, source_scene_id uuid).
- `character_campaign_runs` (character_id fk, campaign_run_id fk, role text, pk(character_id, campaign_run_id)).
- `character_events` (id bigserial pk, character_id fk null, party_id fk null, campaign_run_id fk, world_event_type text, importance text, payload jsonb, timestamp timestamptz).
- `adventure_summaries` (campaign_run_id pk fk, summary jsonb, retcon_package jsonb, created_at).

## Сервисные слои
- **DBProvider**: init pool/connection, apply `CREATE TABLE IF NOT EXISTS` миграции.
- **Repositories**: отдельные классы для players/characters/parties/campaigns/scenes/events; транзакции через context manager.
- **PlayerService**: resolve/create Player по telegram_id, last_login_at update.
- **CharacterService**: CRUD + статус RETIRED/DEAD, валидация владельца, связывание с runs.
- **PartyService**: создание/листинг партий по персонажам игрока, join/leave с проверками ролей/лидера.
- **ChronicleService**: запись CharacterEvent (MICRO/MESO/MACRO).
- **CampaignEngine**:
  - загрузка `CampaignTemplate` из YAML (id/title/season, сцены→Episode).
  - стейт-машина INIT → SCENE → RESOLVE → APPLY_EFFECTS → NEXT/EPILOGUE → COMPLETED.
  - интеграция с Genlayers profiles (`scene.v1`, `combat.v1`, `social.v1`, `epilogue.v1`) с graceful fallback на статический YAML.
  - обновление FlagState, SceneState, CharacterEvent при action.
  - формирование AdventureSummary + RetconPackage при завершении и запись в `adventure_summaries`.

## API (gateway_api)
- Auth dependency: decode JWT (`sub`=telegram_id) → Player resolution.
- `GET /v1/me` → Player + краткие Characters.
- Characters: `GET /v1/characters`, `POST /v1/characters`, `PATCH /v1/characters/{id}`, `POST /v1/characters/{id}/retire`.
- Parties: `GET /v1/parties`, `POST /v1/parties` (leader), `POST /v1/parties/{id}/join`, `POST /v1/parties/{id}/leave`.
- Campaigns: `GET /v1/campaigns` (templates), `POST /v1/campaign-runs` (template_id, party_id), `GET /v1/campaign-runs/{id}`, `POST /v1/campaign-runs/{id}/action`, `GET /v1/campaign-runs/{id}/summary`.
- Контракты/OpenAPI: обновить схемы под новые модели/эндпоинты (rpg-bot.yaml + jsonschema).

## Тесты
- Юниты: сервисы (Player/Character/Party), CampaignEngine (init → scene → action → complete), ChronicleService.
- Интеграция FastAPI (TestClient): happy-path сценарий новый игрок → персонаж → партия → старт кампании → 2 actions → summary.
- Контракты: jsonschema валидация ответов generation/scene уже есть; добавить для новых DTO.

## Открытые вопросы/допущения
- Хранилище по умолчанию: in-memory для тестов; Postgres включается при наличии DSN (переменные окружения). Нужно будет вынести миграции в отдельный инструмент позже.
- Party Sync интеграция с Engine (WS хуки) отложена до Wave 05, но API Engine готовит события для публикации.
- Retcon Engine ingestion остаётся на Wave OBT-2 (RetconPackage только сохраняем/отдаём через API).
