"""Маршруты Gateway API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from ..rate_limit import rate_limit

from ..auth.telegram import InitDataValidationError, InitDataValidator
from ..config import HealthPayload, Settings, get_settings
from ..jwt_utils import issue_access_token
from ..models import AccessTokenResponse, GenerationRequest, TelegramAuthRequest

router = APIRouter()


@router.get("/health", response_model=HealthPayload, tags=["system"])
def read_health(settings: Settings = Depends(get_settings)) -> HealthPayload:
    """Возвращает статус здоровья сервиса."""

    return HealthPayload(status="ok", api_version=settings.api_version)


@router.get("/v1/knowledge/search", tags=["knowledge"])
def search_knowledge(
    request: Request,
    q: str = Query(..., min_length=2, alias="q"),
    top_k: int = Query(5, ge=1, le=20),
    _rl: None = Depends(rate_limit),
) -> dict[str, list[dict[str, Any]]]:
    """Поиск в базе знаний Memory37."""

    service = getattr(request.app.state, "knowledge_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Knowledge search unavailable")

    results = service.search(q, top_k=top_k)
    return {"items": [item.model_dump() for item in results]}


@router.post("/v1/generation/{profile}", tags=["generation"])
def generate_content(
    profile: str,
    payload: GenerationRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> dict[str, Any]:
    """Генерация структурированного контента по профилю."""

    service = getattr(request.app.state, "generation_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Generation service unavailable")
    if profile not in service.profiles():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation profile not found")

    try:
        result = service.generate(profile, payload.prompt)
    except Exception as exc:  # pragma: no cover - пробрасываем ошибку наружу
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {"profile": profile, "result": result}


@router.get("/v1/generation/profiles", tags=["generation"])
def list_generation_profiles(request: Request) -> dict[str, list[str]]:
    """Возвращает список доступных профилей генерации."""

    service = getattr(request.app.state, "generation_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Generation service unavailable")
    return {"profiles": service.profiles()}


@router.get("/v1/generation/profiles/{profile}", tags=["generation"])
def get_generation_profile(profile: str, request: Request) -> dict[str, Any]:
    """Возвращает информацию о профиле генерации."""

    service = getattr(request.app.state, "generation_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Generation service unavailable")
    try:
        detail = service.profile_detail(profile)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation profile not found") from None
    return detail


@router.post(
    "/v1/auth/telegram",
    response_model=AccessTokenResponse,
    tags=["auth"],
    status_code=status.HTTP_200_OK,
)
def exchange_init_data(
    payload: TelegramAuthRequest,
    settings: Settings = Depends(get_settings),
) -> AccessTokenResponse:
    """Обменивает Telegram initData на короткоживущий access token."""

    validator = InitDataValidator(bot_token=settings.bot_token)
    try:
        validated = validator.validate(payload.init_data)
    except InitDataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    access_token, expires_in = issue_access_token(
        settings=settings,
        subject=str(validated.user.id),
        extra={
            "query_id": validated.query_id,
            "chat_id": validated.chat.id if validated.chat else None,
            "language_code": validated.user.language_code,
        },
    )

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        issued_at=datetime.now(tz=UTC),
        user=validated.user,
        chat=validated.chat,
    )
