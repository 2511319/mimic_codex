"""Маршруты Gateway API."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth.telegram import InitDataValidationError, InitDataValidator
from ..config import HealthPayload, Settings, get_settings
from ..jwt_utils import issue_access_token
from ..models import AccessTokenResponse, TelegramAuthRequest

router = APIRouter()


@router.get("/health", response_model=HealthPayload, tags=["system"])
def read_health(settings: Settings = Depends(get_settings)) -> HealthPayload:
    """Возвращает статус здоровья сервиса."""

    return HealthPayload(status="ok", api_version=settings.api_version)


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
