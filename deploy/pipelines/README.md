# Codex Run in the cloud

Пайплайн предназначен для запуска задач Codex в облачной среде. Он выполняет следующие шаги:

1. Сборка Docker-образа сервиса `gateway_api`.
2. Прогон `poetry run pytest` и `npm run lint`.
3. Публикация образа в контейнерный регистр.
4. Развёртывание в стадию `staging` через Blue-Green.

Переменные окружения описаны в `cloud-run.yaml`. Секреты должны храниться в Secret Manager.
