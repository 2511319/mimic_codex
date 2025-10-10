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
