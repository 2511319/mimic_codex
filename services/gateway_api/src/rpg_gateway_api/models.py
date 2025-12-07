"""Pydantic-модели публичного API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

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


class SceneGenerateRequest(BaseModel):
    """Запрос на доменную генерацию сцены/боёвки/социального взаимодействия."""

    model_config = ConfigDict(populate_by_name=True)

    prompt: str = Field(..., min_length=2, description="Человеко-читаемое описание ситуации/контекста")
    campaign_id: str | None = Field(None, alias="campaignId")
    party_id: str | None = Field(None, alias="partyId")
    scene_id: str | None = Field(None, alias="sceneId")
    language: str | None = Field(None, description="ISO-код языка")


class SceneGenerateResponse(BaseModel):
    """Ответ генерации с использованием доменного профиля."""

    model_config = ConfigDict(populate_by_name=True)

    profile: str
    result: dict[str, Any]
    knowledge_items: list[dict[str, Any]] = Field(default_factory=list, alias="knowledgeItems")


__all__ = [
    "TelegramAuthRequest",
    "AccessTokenResponse",
    "InitDataPayload",
    "TelegramUser",
    "TelegramChat",
    "GenerationRequest",
    "SceneGenerateRequest",
    "SceneGenerateResponse",
]
