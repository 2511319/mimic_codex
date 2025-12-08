"""Конфигурация сервиса Gateway API."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Параметры окружения для Gateway API."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = Field(..., min_length=10, description="Telegram Bot API token")
    jwt_secret: str = Field(..., min_length=16, description="Секрет подписи JWT")
    jwt_algorithm: Literal["HS256"] = Field("HS256", description="Алгоритм подписи JWT")
    jwt_ttl_seconds: int = Field(900, ge=60, le=3600, description="Время жизни access token")
    api_version: str = Field("1.0.0", description="Версия API, возвращаемая в health-check")
    knowledge_source_path: str | None = Field(
        None,
        description="Path to Memory37 knowledge YAML",
        alias="KNOWLEDGE_SOURCE_PATH",
    )
    knowledge_use_openai: bool = Field(
        False,
        description="Use OpenAI embeddings for Memory37",
        alias="KNOWLEDGE_USE_OPENAI",
    )
    knowledge_openai_embedding_model: str | None = Field(
        None,
        description="OpenAI embedding model override",
        alias="KNOWLEDGE_OPENAI_EMBEDDING_MODEL",
    )
    openai_api_key: str | None = Field(
        None,
        description="OpenAI API key",
        alias="OPENAI_API_KEY",
    )
    openai_model: str = Field(
        "gpt-5-nano",
        description="OpenAI model for structured generation",
        alias="OPENAI_MODEL",
    )
    openai_timeout_seconds: float = Field(
        120.0,
        ge=1.0,
        description="OpenAI Responses timeout, seconds",
        alias="OPENAI_TIMEOUT_SECONDS",
    )
    generation_profiles_path: str = Field(
        "profiles.yaml",
        description="Path to genlayers profiles YAML",
        alias="GENERATION_PROFILES_PATH",
    )
    generation_schema_root: str = Field(
        "contracts/jsonschema",
        description="Directory with JSON Schemas for generation",
        alias="GENERATION_SCHEMA_ROOT",
    )
    generation_max_retries: int = Field(
        2,
        ge=0,
        description="Max retries for structured generation",
        alias="GENERATION_MAX_RETRIES",
    )
    knowledge_openai_rerank_model: str | None = Field(
        None,
        description="OpenAI rerank model override",
        alias="KNOWLEDGE_OPENAI_RERANK_MODEL",
    )
    knowledge_database_url: str | None = Field(
        None,
        description="PostgreSQL DSN для хранилища знаний",
        alias="KNOWLEDGE_DATABASE_URL",
    )
    knowledge_vector_table: str = Field(
        "memory37_vectors",
        description="Таблица pgvector",
        alias="KNOWLEDGE_VECTOR_TABLE",
    )
    knowledge_vector_dimension: int = Field(
        1536,
        description="Размерность вектора",
        alias="KNOWLEDGE_VECTOR_DIMENSION",
    )
    neo4j_uri: str | None = Field(
        None,
        description="Neo4j URI для GraphRAG (bolt://...)",
        alias="NEO4J_URI",
    )
    neo4j_user: str | None = Field(
        None,
        description="Neo4j user",
        alias="NEO4J_USER",
    )
    neo4j_password: str | None = Field(
        None,
        description="Neo4j password",
        alias="NEO4J_PASSWORD",
    )
    neo4j_database: str | None = Field(
        None,
        description="Neo4j database name (optional)",
        alias="NEO4J_DATABASE",
    )
    knowledge_version_id: str | None = Field(
        None,
        description="Идентификатор версии знаний (для фильтрации результатов)",
        alias="KNOWLEDGE_VERSION_ID",
    )
    knowledge_version_alias: str | None = Field(
        None,
        description="Алиас версии знаний (например, lore_latest)",
        alias="KNOWLEDGE_VERSION_ALIAS",
    )
    database_url: str | None = Field(
        None,
        description="PostgreSQL DSN для основного хранилища (опционально, по умолчанию in-memory)",
        alias="DATABASE_URL",
    )
    database_fallback_to_memory: bool = Field(
        True,
        description="Разрешить откат на in-memory хранилище при недоступности Postgres",
        alias="DATABASE_FALLBACK_TO_MEMORY",
    )

    # Rate limiting (optional, disabled by default)
    rate_limit_enabled: bool = Field(
        False,
        description="Enable in-app rate limit for selected endpoints",
        alias="RATE_LIMIT_ENABLED",
    )
    rate_limit_rps: float = Field(
        1.0,
        ge=0.1,
        description="Requests per second per key for rate-limited endpoints",
        alias="RATE_LIMIT_RPS",
    )
    rate_limit_burst: int = Field(
        3,
        ge=1,
        description="Burst capacity for token bucket",
        alias="RATE_LIMIT_BURST",
    )
    party_sync_base_url: str | None = Field(
        None,
        description="Base URL для party_sync (например, http://localhost:8001)",
        alias="PARTY_SYNC_BASE_URL",
    )


class HealthPayload(BaseModel):
    """Ответ health-check."""

    status: Literal["ok"]
    api_version: str


@lru_cache
def get_settings() -> Settings:
    """Загружает настройки с кешированием.

    Returns:
        Settings: Экземпляр настроек приложения.
    """

    return Settings()
