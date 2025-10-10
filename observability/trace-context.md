# Trace Context & OpenTelemetry

- Заголовки: `traceparent`, `tracestate` обязательны для всех запросов.
- FastAPI middleware (`observability.middleware.TraceMiddleware`) добавит `trace_id` в лог.
- Метрики (`service_request_duration_seconds`) публикуем в Prometheus формата.
- Логи отправляются в JSON через stdout.

## Настройка локально

```bash
poetry run uvicorn rpg_gateway_api.app:create_app --factory --reload --log-config observability/logging.json
```
