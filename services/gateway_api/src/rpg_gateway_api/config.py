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
