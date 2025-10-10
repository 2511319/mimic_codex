# RPG-Bot Codex Monorepo

Проект подготовлен для разработки текстового RPG в Telegram Mini App по стандартам «гласов» 1–10 и с учётом режима Codex **Run in the cloud**. Репозиторий структурирован как монорепозиторий с контрактами, сервисами, пакетами и web-клиентом, а также с готовыми настройками CI/CD, тестами и документацией.

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
- `apps/webapp/` — Telegram Mini App (Vite + React + TypeScript) с health-виджетом и lint-скриптами.
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
- `poetry run uvicorn rpg_media_broker.app:create_app --factory --reload`
- `poetry run ruff check`
- `poetry run mypy services`
- `npm run dev --prefix apps/webapp`

## Документация

- Геймдизайн и UX: главы `Глава 1` – `Глава 2`
- Системный дизайн и данные: главы `Глава 3` – `Глава 5`
- Операции и процесс: главы `Глава 6` – `Глава 10`
- ADR-шаблон: `docs/ADRs/0000-template.md`

Перед отправкой изменений убедитесь, что пройдены все проверки CI и обновлены артефакты (контракты, тесты, документация). Это позволит безболезненно запускать задачи через Codex как локально, так и в облачном режиме.
"# mimic" 
