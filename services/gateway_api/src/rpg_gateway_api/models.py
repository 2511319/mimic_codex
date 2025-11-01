"""Pydantic-модели публичного API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .auth.telegram import InitDataPayload, TelegramChat, TelegramUser


class TelegramAuthRequest(BaseModel):
    """Запрос авторизации через Telegram initData."""

    model_config = ConfigDict(populate_by_name=True)

    init_data: str = Field(..., alias="initData", min_length=10)


class AccessTokenResponse(BaseModel):
    """Ответ при успешной авторизации."""

    model_config = ConfigDict(populate_by_name=True)

    access_token: str = Field(..., alias="accessToken")
    token_type: str = Field("Bearer", alias="tokenType")
    expires_in: int = Field(..., alias="expiresIn", ge=60)
    issued_at: datetime = Field(..., alias="issuedAt")
    user: TelegramUser
    chat: TelegramChat | None = None


class GenerationRequest(BaseModel):
    """Запрос на генерацию контента."""

    prompt: str = Field(..., min_length=2)


__all__ = [
    "TelegramAuthRequest",
    "AccessTokenResponse",
    "InitDataPayload",
    "TelegramUser",
    "TelegramChat",
    "GenerationRequest",
]
