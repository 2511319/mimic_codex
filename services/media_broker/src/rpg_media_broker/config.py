"""Configuration for media broker service."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment settings for media broker."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_version: str = Field("1.0.0", description="API version exposed via health endpoint.")
    worker_concurrency: int = Field(1, ge=1, le=8, description="Number of async worker tasks.")
    processing_delay_ms: int = Field(
        50,
        ge=0,
        le=60000,
        description="Artificial processing delay used for deterministic tests.",
    )
    job_history_limit: int = Field(
        1000,
        ge=1,
        le=10000,
        description="Limit on in-memory job history entries.",
    )


class HealthPayload(BaseModel):
    """Health response payload."""

    status: Literal["ok"]
    api_version: str


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
