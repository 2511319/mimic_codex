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

    # Optional in-app rate limit (dev/staging)
    rate_limit_enabled: bool = Field(
        False,
        description="Enable in-app rate limit for POST /v1/media/jobs",
        alias="RATE_LIMIT_ENABLED",
    )
    rate_limit_rps: float = Field(
        2.0,
        ge=0.1,
        description="Requests per second per key",
        alias="RATE_LIMIT_RPS",
    )
    rate_limit_burst: int = Field(
        4,
        ge=1,
        description="Burst capacity for token bucket",
        alias="RATE_LIMIT_BURST",
    )


class HealthPayload(BaseModel):
    """Health response payload."""

    status: Literal["ok"]
    api_version: str


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
