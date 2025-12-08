"""Pydantic-модели публичного API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

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


class PlayerProfile(BaseModel):
    """Модель игрока в публичном API."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    telegram_id: int = Field(..., alias="telegramId")
    display_name: str = Field(..., alias="displayName")
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(..., alias="createdAt")
    last_login_at: datetime = Field(..., alias="lastLoginAt")


class CharacterPayload(BaseModel):
    """Модель персонажа."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    player_id: int = Field(..., alias="playerId")
    name: str
    archetype: str
    race: str | None = None
    level: int
    xp: int
    core_stats: dict[str, Any] = Field(default_factory=dict, alias="coreStats")
    skills: dict[str, Any] = Field(default_factory=dict)
    inventory_ref: str | None = Field(None, alias="inventoryRef")
    status: str
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")


class CharacterCreateRequest(BaseModel):
    """Запрос на создание персонажа."""

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., min_length=2)
    archetype: str = Field(..., min_length=2)
    race: str | None = None
    core_stats: dict[str, Any] | None = Field(default=None, alias="coreStats")
    skills: dict[str, Any] | None = None


class CharacterUpdateRequest(BaseModel):
    """Запрос на частичное обновление персонажа."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=2)
    archetype: str | None = Field(default=None, min_length=2)
    race: str | None = None


class PartyPayload(BaseModel):
    """Модель партии."""

    model_config = ConfigDict(populate_by_name=True)

    id: int
    name: str | None = None
    leader_character_id: int = Field(..., alias="leaderCharacterId")
    active_campaign_run_id: str | None = Field(None, alias="activeCampaignRunId")
    created_at: datetime = Field(..., alias="createdAt")


class PartyCreateRequest(BaseModel):
    """Создание партии."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = None
    leader_character_id: int = Field(..., alias="leaderCharacterId", ge=1)


class PartyMemberRequest(BaseModel):
    """Запрос на join/leave."""

    model_config = ConfigDict(populate_by_name=True)

    character_id: int = Field(..., alias="characterId", ge=1)


class MeResponse(BaseModel):
    """Профиль игрока и его персонажи."""

    model_config = ConfigDict(populate_by_name=True)

    player: PlayerProfile
    characters: List[CharacterPayload] = Field(default_factory=list)


class CampaignTemplatePayload(BaseModel):
    """Доступный шаблон кампании."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    description: str
    season_version: str = Field(..., alias="seasonVersion")
    metadata: dict[str, Any] = Field(default_factory=dict)


class SceneStatePayload(BaseModel):
    """Состояние сцены."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    episode_id: str = Field(..., alias="episodeId")
    scene_order: int = Field(..., alias="sceneOrder")
    scene_type: str = Field(..., alias="sceneType")
    profile: str | None = None
    generated_payload: dict[str, Any] = Field(default_factory=dict, alias="generatedPayload")
    resolved: bool
    result_flags: dict[str, Any] = Field(default_factory=dict, alias="resultFlags")


class CampaignRunPayload(BaseModel):
    """Состояние CampaignRun."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    campaign_template_id: str = Field(..., alias="campaignTemplateId")
    party_id: int = Field(..., alias="partyId")
    status: str
    current_episode_id: str | None = Field(None, alias="currentEpisodeId")
    current_scene_id: str | None = Field(None, alias="currentSceneId")
    created_at: datetime = Field(..., alias="createdAt")
    finished_at: datetime | None = Field(None, alias="finishedAt")
    current_scene: SceneStatePayload | None = Field(None, alias="currentScene")


class CampaignRunCreateRequest(BaseModel):
    """Запуск CampaignRun."""

    model_config = ConfigDict(populate_by_name=True)

    campaign_template_id: str = Field(..., alias="campaignTemplateId", min_length=2)
    party_id: int = Field(..., alias="partyId", ge=1)
    character_ids: list[int] | None = Field(default=None, alias="characterIds")


class CampaignActionRequest(BaseModel):
    """Действие в рамках сцены."""

    model_config = ConfigDict(populate_by_name=True)

    action_type: str = Field(..., alias="actionType", min_length=2)
    payload: dict[str, Any] | None = None


class CampaignSummaryResponse(BaseModel):
    """AdventureSummary + RetconPackage."""

    model_config = ConfigDict(populate_by_name=True)

    adventure_summary: dict[str, Any] = Field(..., alias="adventureSummary")
    retcon_package: dict[str, Any] = Field(..., alias="retconPackage")


__all__ = [
    "TelegramAuthRequest",
    "AccessTokenResponse",
    "InitDataPayload",
    "TelegramUser",
    "TelegramChat",
    "GenerationRequest",
    "SceneGenerateRequest",
    "SceneGenerateResponse",
    "PlayerProfile",
    "CharacterPayload",
    "CharacterCreateRequest",
    "CharacterUpdateRequest",
    "PartyPayload",
    "PartyCreateRequest",
    "PartyMemberRequest",
    "MeResponse",
    "CampaignTemplatePayload",
    "SceneStatePayload",
    "CampaignRunPayload",
    "CampaignRunCreateRequest",
    "CampaignActionRequest",
    "CampaignSummaryResponse",
]
