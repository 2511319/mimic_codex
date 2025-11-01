"""Configuration for Party Sync service."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment configuration."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_version: str = Field("1.0.0", description="Semantic version returned by health endpoints.")
    max_connections_per_campaign: int = Field(
        32,
        ge=1,
        le=500,
        description="Safety cap for simultaneous websocket connections per campaign.",
    )
    broadcast_history_limit: int = Field(
        50,
        ge=1,
        le=500,
        description="Number of last events retained for late subscribers.",
    )

    # Optional in-app rate limit (dev/staging)
    rate_limit_enabled: bool = Field(
        False,
        description="Enable in-app rate limit for broadcast endpoint",
        alias="RATE_LIMIT_ENABLED",
    )
    rate_limit_rps: float = Field(
        2.0,
        ge=0.1,
        description="Requests per second per key",
        alias="RATE_LIMIT_RPS",
    )
    rate_limit_burst: int = Field(
        5,
        ge=1,
        description="Burst capacity for token bucket",
        alias="RATE_LIMIT_BURST",
    )


class HealthPayload(BaseModel):
    """Health-check response payload."""

    status: Literal["ok"]
    api_version: str


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance.

    Returns:
        Settings: Loaded environment settings.
    """

    return Settings()
