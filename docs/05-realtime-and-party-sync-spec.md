# RPG-Bot — Реалтайм и party-sync  
## 05. Realtime / Party Sync / Protocol

## 1. Цель

Довести сервис `party_sync` до боевого уровня:

- устойчивый мультиплеер (несколько игроков в одной кампании);
- единый протокол событий через WebSocket + backend-транспорт (Redis);
- интеграция c Campaign Engine и летописями.

## 2. Архитектурный обзор

Компоненты:

- `services/party_sync`:
  - WebSocket-шлюз для клиентов (UI Mini-App);
  - слой авторизации/валидации;
  - взаимодействие с Redis (pub/sub) для доставки событий.

- Redis:
  - каналы per-party / per-campaign_run;
  - хранение короткоживущего состояния при необходимости.

- Campaign Engine:
  - получает действия игроков (через gateway_api),
  - отправляет системные события (результаты сцен, изменения стейтов) в party_sync.

## 3. Каналы и идентификация

- Канал WS для клиента привязан к:
  - `party_id`,
  - `campaign_run_id`,
  - `character_id`.

- Внутри Redis:
  - канал `party:<party_id>` — широковещательные события;
  - опционально канал `run:<campaign_run_id>`.

## 4. Формат сообщений (WS Payload)

Базовый формат:

```json
{
  "type": "string",
  "timestamp": "...",
  "trace_id": "...",
  "payload": { ... }
}
Типы:

system.hello

system.error

party.join

party.leave

party.state

action.request

action.result

vote.started

vote.update

vote.finished

combat.update

scene.update

Каждый payload описывается отдельной JSON Schema (лежит в contracts/jsonschema/party_sync/**).

## 5. Примеры ключевых payload
5.1. Подключение
system.hello (сервер → клиент):

текущий статус party/run,

список участников,

номер текущей сцены.

5.2. Join / Leave
party.join:

character_id

display_name

party.leave:

character_id

5.3. Действия игроков
action.request (клиент → сервер → gateway_api/Campaign Engine):

action_id

character_id

campaign_run_id

action_type (выбор, боевое действие, skill-check),

payload.

action.result (сервер → клиенты):

результат действия (успех/провал/частичный успех),

обновлённый state (hp, эффекты, флаги сцены).

5.4. Голосование
vote.started:

vote_id

options (A/B/C),

timeout.

vote.update:

текущие голоса по опциям.

vote.finished:

победившая опция,

как она будет применена к Campaign Engine.

## 6. Интеграция с Campaign Engine
Все игровые решения проходят через gateway_api → Campaign Engine.

Party_sync:

не принимает окончательных решений,

отвечает за:

доставку action.request от клиентов,

трансляцию action.result и scene.update.

Campaign Engine в свою очередь:

после применения решения:

обновляет L1/L2,

отправляет системное событие в party_sync (scene.update, combat.update).

## 7. Устойчивость и reconnect
Требования:

поддержка reconnect-логики:

при переподключении клиент получает system.hello с текущим состоянием;

предотвращение “двойных” действий:

idempotency по action_id;

простой механизм блокировки повторных отправок.

## 8. Definition of Done
Определён JSON-протокол с описанными типами сообщений и payload’ами.

Реализован WS-сервер в party_sync с авторизацией и подпиской на party:<party_id>.

Интеграция Redis для pub/sub.

Campaign Engine умеет отправлять события в party_sync и принимать действия игроков.

Написаны базовые тесты:

два клиента подключаются к одной party,

один делает действие, второй видит его результат и обновление сцены.

swift
Копировать код

---