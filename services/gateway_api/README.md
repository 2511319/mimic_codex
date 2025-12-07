# Gateway API

FastAPI-сервис, отвечающий за обмен Telegram initData на JWT. Предусмотрены:

- `/v1/auth/telegram` — POST, принимает initData.
- `/health` — GET, статус сервиса.
- `/config` — GET, версия конфигурации.

Локальный запуск:

```bash
poetry run uvicorn rpg_gateway_api.app:create_app --factory --reload
```

Переменные окружения описаны в `.env.example`.

## Memory37 knowledge search

- `KNOWLEDGE_SOURCE_PATH` — путь до YAML знаний (см. `data/knowledge/sample.yaml`), загружается в in-memory при старте.
- `KNOWLEDGE_DATABASE_URL` + `KNOWLEDGE_VECTOR_TABLE` — если заданы и установлен `psycopg`, используется `PgVectorWrapper`.
- Версии: `KNOWLEDGE_VERSION_ID`/`KNOWLEDGE_VERSION_ALIAS` фильтруют выдачу.
- Эндпоинт: `GET /v1/knowledge/search?q=...&top_k=5` (async, гибрид vector+lexical).
