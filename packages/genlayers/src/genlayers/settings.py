"""Настройки для инициализации движка genlayers."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class GenerationSettings(BaseSettings):
    """Параметры запуска движка структурированной генерации."""

    profiles_path: Path = Field(alias="profilesPath")
    schema_root: Path = Field(default=Path("contracts/jsonschema"), alias="schemaRoot")
    openai_model: str = Field(default="gpt-4.1", alias="openaiModel")
    openai_api_key: str | None = Field(default=None, alias="openaiApiKey")
    openai_timeout: float = Field(default=120.0, ge=1.0, alias="openaiTimeout")
    max_retries: int = Field(default=2, ge=0, alias="maxRetries")

    model_config = SettingsConfigDict(env_prefix="GENLAYERS_", populate_by_name=True)
