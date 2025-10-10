FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --upgrade pip && pip install poetry==1.8.3

COPY pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --only main --no-interaction

COPY services/gateway_api ./services/gateway_api
COPY packages ./packages
COPY contracts ./contracts
COPY config/knowledge ./config/knowledge

CMD ["uvicorn", "rpg_gateway_api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
