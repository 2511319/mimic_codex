FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --upgrade pip && pip install poetry==1.8.3

COPY pyproject.toml ./
COPY services/party_sync ./services/party_sync
COPY packages ./packages
COPY observability ./observability

ENV PYTHONPATH="/app/services/gateway_api/src:/app/services/party_sync/src:/app/services/media_broker/src:/app/packages/memory37/src:/app/packages/genlayers/src:/app/packages/rpg_contracts/src:${PYTHONPATH}"
RUN poetry config virtualenvs.create false && poetry install --only main --no-interaction

CMD ["uvicorn", "rpg_party_sync.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8081"]
