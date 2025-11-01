# RPG-Bot Codex Monorepo

Проект подготовлен для разработки текстового RPG в Telegram Mini App по стандартам Глав 1–10 и с учётом режима Codex **Run in the cloud**. Репозиторий структурирован как монорепозиторий с контрактами, сервисами, пакетами и web-клиентом, а также с готовыми настройками CI/CD, тестами и документацией.

## Быстрый старт

1. Установите Python 3.12+, Poetry 1.8+, Node.js 20+.
2. Создайте `.env` из `.env.example` и заполните секреты (`BOT_TOKEN`, `JWT_SECRET` и т.д.).
3. Выполните `poetry install` в корне репозитория.
4. Выполните `npm install` в `apps/webapp`.
5. Запустите проверки локально:
   - `poetry run pytest`
   - `npm run lint --prefix apps/webapp`

## Структура

- `contracts/` — OpenAPI 3.1 + JSON Schema + CloudEvents, из которых генерируются SDK.
- `services/gateway_api/` — FastAPI-сервис авторизации Mini App (initData → JWT) и health-check.
- `services/party_sync/` — WebSocket-хаб синхронизации партий (голосование, таймеры, ретрансляция событий).
- `services/media_broker/` — брокер медиа-заданий (TTS/IMG/Avatar) с асинхронными воркерами и идемпотентными API.
- `packages/memory37/` — библиотека конфигураций и валидации индексов знаний («Память37»).
- `packages/genlayers/` — профили генеративных слоёв и шаблонов (structured outputs).
- `packages/rpg_contracts/` — утилиты для работы с контрактами внутри Python.
- `apps/webapp/` — Telegram Mini App (Vite + React + TypeScript) с health-виджетом, feature-модулями Party/Media/Generation и lint-скриптами.
- `qa/`, `config/`, `observability/`, `deploy/`, `security/` — артефакты по главам 5–10.
- `.github/workflows/` — пайплайн CI (Poetry/pytest, npm lint, Spectral).

## Run in the cloud

Функция Codex **Run in the cloud** использует контейнеры со стандартным набором инструментов:

- инфраструктура описана в `deploy/pipelines/cloud-run.yaml`;
- пайплайн собирает Docker-образы сервисов из `services/`, прогоняет тесты и выкладывает в регистр;
- переменные окружения и секреты прокидываются через `.env` или секрет-хранилище (см. `deploy/pipelines/README.md`).

## Команды разработчика

- `poetry run uvicorn rpg_gateway_api.app:create_app --factory --reload`
- `poetry run uvicorn rpg_party_sync.app:create_app --factory --reload`
- `python -m memory37.cli search "moon" --knowledge-file data/knowledge/sample.yaml --dry-run`
- `python -m genlayers.cli scene --prompt "Describe scene" --config profiles.yaml --schema-root contracts/jsonschema`
- `poetry run uvicorn rpg_media_broker.app:create_app --factory --reload`
- `poetry run ruff check`
- `poetry run mypy services`
- `npm run dev --prefix apps/webapp`

### Переменные окружения (минимум)

- `API_VERSION` — строка версии API в `/health` и `/config`
- `BOT_TOKEN`, `JWT_SECRET`, `JWT_TTL_SECONDS` — авторизация Mini App (initData → JWT)
- `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_TIMEOUT_SECONDS` — генерация (genlayers)
- `GENERATION_PROFILES_PATH`, `GENERATION_SCHEMA_ROOT`, `GENERATION_MAX_RETRIES` — профили/схемы
- `KNOWLEDGE_SOURCE_PATH` — YAML‑файл знаний для Memory37 (альтернатива — `KNOWLEDGE_DATABASE_URL`)
- `KNOWLEDGE_USE_OPENAI`, `KNOWLEDGE_OPENAI_EMBEDDING_MODEL` — провайдеры embeddings (опционально)
 - `VITE_API_BASE_URL` — базовый URL API для WebApp (опционально)
 - `VITE_PARTY_WS_URL` — явный WS‑URL для Party (если отличается от API) (опционально)
 - `VITE_MEDIA_BASE_URL` — базовый URL сервиса Media Broker (если отличается от API) (опционально)

#### In‑app rate limit (dev/staging)

Для `gateway_api`, `party_sync`, `media_broker` доступны одинаковые ключи (по умолчанию выключены):

- `RATE_LIMIT_ENABLED=false` — включение лимитера
- `RATE_LIMIT_RPS` — скорость пополнения (req/sec на ключ)
- `RATE_LIMIT_BURST` — burst‑ёмкость бакета

Лимитируются:
- Gateway: `POST /v1/generation/{profile}`
- Party: `POST /v1/campaigns/{id}/broadcast`
- Media: `POST /v1/media/jobs`

### Смоук‑проверки (локально)

- Для каждого сервиса доступен `/config` c `apiVersion` и `traceId` для быстрой корреляции запросов.
- `GET /health` во всех сервисах возвращает `{ status: "ok", api_version }`.
- Gateway API:
  - `GET /v1/generation/profiles`, `GET /v1/generation/profiles/{profile}` — профили генерации
  - `POST /v1/generation/{profile}` с `{ prompt }` — валидный JSON по схеме
  - `GET /v1/knowledge/search?q=moon` — результаты поиска при наличии источника знаний
- Party Sync: WebSocket `/ws/campaign/{id}` — соединение, рассылка и реплей истории
- Media Broker: `/v1/media/jobs` — постановка и отслеживание задач (in‑memory)

См. подробности: `docs/runbooks/smoke-tests.md` и `docs/runbooks/ui-smoke.md`.

CLI смоук проверка сервисов:

```
python tools/smoke.py --gateway http://localhost:8000 --party http://localhost:8001 --media http://localhost:8002
```

## Genlayers CLI

- CLI `python -m genlayers.cli <profile>` запускает структурированную генерацию по профилю из `profiles.yaml` с валидацией контрактов.
- Для запуска используйте `python -m genlayers.cli scene --prompt "Describe scene" --config profiles.yaml --schema-root contracts/jsonschema`.
- Перед запуском установите `GENLAYERS_OPENAI_MODEL=gpt-4.1` и `GENLAYERS_OPENAI_API_KEY=<token>` (или передайте значения флагами CLI).
- Доступные флаги CLI: `--max-retries`, `--openai-timeout`, `--prompt-file`; см. `python -m genlayers.cli --help`.
- REST: `/v1/generation/profiles` (список профилей), `/v1/generation/{profile}` (генерация по профилю и промпту).
- Профили по умолчанию (`profiles.yaml`) включают `scene.v1`, `social.v1`, `combat.v1`, `epilogue.v1`, и ссылаются на схемы в `contracts/jsonschema`.

## Документация

- Геймдизайн и UX: главы `Глава 1` – `Глава 2`
- Системный дизайн и данные: главы `Глава 3` – `Глава 5`
- Операции и процесс: главы `Глава 6` – `Глава 10`
- ADR-шаблон: `docs/ADRs/0000-template.md`
 - План закрытия до 100%: `docs/roadmap/closure-plan.md`

Перед отправкой изменений убедитесь, что пройдены все проверки CI и обновлены артефакты (контракты, тесты, документация). Это позволит безболезненно запускать задачи через Codex как локально, так и в облачном режиме.

## Knowledge search

- Set `KNOWLEDGE_SOURCE_PATH` to YAML (e.g. `data/knowledge/sample.yaml`).
- Optional: set `KNOWLEDGE_USE_OPENAI=true` and `OPENAI_MODEL`/`OPENAI_EMBEDDING_MODEL` for OpenAI embeddings.
- Restart `gateway_api` and call `/v1/knowledge/search?q=moon`.
- Используйте `python -m memory37.cli ingest-file data/knowledge/sample.yaml --use-openai` для загрузки знаний в pgvector (требует `MEMORY37_DATABASE_URL`).
- При наличии `KNOWLEDGE_DATABASE_URL` Gateway обращается к pgvector и не выполняет загрузку YAML при старте.
