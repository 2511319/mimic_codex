FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --upgrade pip && pip install poetry==1.8.3

COPY pyproject.toml ./
# Copy sources and artifacts required at runtime
COPY services/gateway_api ./services/gateway_api
COPY packages ./packages
COPY contracts ./contracts
COPY config/knowledge ./config/knowledge
COPY data/knowledge ./data/knowledge

# Ensure Python can resolve in-repo src packages and install dependencies
ENV PYTHONPATH="/app/services/gateway_api/src:/app/services/party_sync/src:/app/services/media_broker/src:/app/packages/memory37/src:/app/packages/genlayers/src:/app/packages/rpg_contracts/src:${PYTHONPATH}"
RUN poetry config virtualenvs.create false && poetry install --only main --no-interaction

CMD ["uvicorn", "rpg_gateway_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
