---
slug: rpg-bot-backend-waveA-report
title: "Wave A: Party Sync v1, Media-broker MVP, Observability baseline — отчёт"
wave: "A"
status: "done"
---

## Изменённые файлы

- services/party_sync: models.py, config.py, hub.py, api/routes.py
- services/media_broker: manager.py, tests/test_media_broker.py
- observability: проверки вызова setup_observability в gateway_api/app.py, party_sync/app.py, media_broker/app.py (без правок логики)

## Тесты, которые запускались

- `python -m pytest services/party_sync -vv` — passed
- `python -m pytest services/media_broker -vv` — passed
- Ручной WS-сценарий (TestClient): два клиента в /ws/campaign/cmp-manual, отправка двух событий, поздний подписчик получил replay и живые сообщения
- Ручной чек метрик: `ENABLE_METRICS=true` / `ENABLE_OTEL=true`, `/metrics` отвечает 200 во всех трёх сервисах (gateway-api, party-sync, media-broker); логи содержат trace_id

## Выполнение DoD (Wave A)

- Party Sync: WS-хаб обслуживает нескольких клиентов, позднее подключение получает историю и новые события — **выполнено**
- Media-broker: POST `/v1/media/jobs` с одинаковым payload без clientToken возвращает один `jobId`; идемпотентность по clientToken — **выполнено**
- Observability: `/metrics` работает при `ENABLE_METRICS=true`; JSON-логи с trace_id; setup_observability вызывается один раз на сервис — **выполнено**
- Тесты `services/party_sync` и `services/media_broker` — **выполнено** (зелёные)
