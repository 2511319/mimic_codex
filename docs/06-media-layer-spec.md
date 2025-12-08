# RPG-Bot — Медиаслой (без TTS)  
## 06. Media Layer: Art / Assets / Media Broker

## 1. Цель

Сделать рабочий медиаслой для OBT:

- арты сцен, NPC, монстров, локаций;
- устойчивый пайплайн через `media_broker`;
- без включения TTS (отложено на пост-OBT).

## 2. Типы медиа в OBT-скоупе

- `SCENE_ART` — иллюстрации для ключевых сцен.
- `LOCATION_ART` — арты локаций/городов.
- `NPC_PORTRAIT` — портреты ключевых NPC.
- `MONSTER_ART` — изображения монстров.
- `ITEM_ICON` — иконки предметов.

Все ассеты либо:

- **pre-generated** (подготавливаются заранее), либо
- **lazy-generated** по запросу, но с кэшированием.

## 3. MediaJob и media_broker

`MediaJob`:

- `id`
- `type` (один из типов медиа)
- `entity_ref` (ссылка: npc_id, monster_id, scene_id, location_id, item_id)
- `requested_at`
- `status` (`PENDING`, `IN_PROGRESS`, `DONE`, `FAILED`)
- `result_url` (ссылка на готовый ассет)
- `provider` (`STATIC`, `GEN`, др.)
- `error` (msg, если FAILED)

`media_broker`:

- REST API:
  - `POST /v1/media/jobs` — создать задачу;
  - `GET  /v1/media/jobs/{id}` — статус;
  - `GET  /v1/media/jobs` — список для отладки/админки.

- Внутренняя очередь:
  - либо таблица БД + polling,
  - либо Redis/очередь.

## 4. Воркеры медиа

Отдельный процесс/сервис:

- читает `MediaJob` со статусом `PENDING`;
- для каждого:

  - если тип `STATIC`:
    - определяется путь до уже подготовленного ассета;
    - записывается `result_url`, статус `DONE`.

  - если тип `GEN`:
    - вызывает внешний провайдер (LLM-изображения);
    - сохраняет изображение в сторедж (S3/аналог);
    - записывает `result_url`, статус `DONE`.

При ошибке — статус `FAILED`, логируется `error`.

## 5. Привязка к контенту и Campaign Engine

В контент-паках:

- у `npc`, `monster`, `location`, `scene` есть поля:

  - `asset_id` (если ассет заранее подготовлен),
  - или `media_spec` (описание, на основе которого можно сделать генерацию).

Campaign Engine:

- при генерации сцены/битвы/социальной сцены:

  - может включать в `SceneResponse`:
    - `scene_art_ref`,
    - `npc_portrait_ref`,
    - `monster_art_ref`.

UI знает, как сопоставить эти ссылки с `MediaJob`/готовыми ассетами.

## 6. Контракты для UI

UI ожидает:

- синхронные ссылки на уже готовые ассеты (pre-gen);
- либо возможность:

  - получить `job_id` и опрашивать `/v1/media/jobs/{id}`,
  - подписаться на событие `media.job.done` (через party_sync или отдельный канал).

Для OBT допустимо:

- использовать pre-gen для большей части контента;
- lazy-gen для ограниченного числа “спецсцен”.

## 7. Definition of Done

- Определён формат `MediaJob`, реализованы endpoint’ы в `media_broker`.  
- Реализован worker, обрабатывающий `PENDING` задачи.  
- Контент Season 1 содержит ссылки `asset_id`/`media_spec` для ключевых сущностей.  
- UI может отображать базовый медиа-слой для сцен/локаций/NPC/монстров.  
- Написаны тесты по пайплайну: создание MediaJob → обработка воркером → `DONE` с `result_url`.