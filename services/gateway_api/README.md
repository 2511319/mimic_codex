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
