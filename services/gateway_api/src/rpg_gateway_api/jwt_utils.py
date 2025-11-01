"""Утилиты для выпуска JWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt

from .config import Settings


def issue_access_token(*, settings: Settings, subject: str, extra: dict[str, Any]) -> tuple[str, int]:
    """Создаёт короткоживущий access token.

    Args:
        settings: Настройки сервиса.
        subject: Идентификатор пользователя (claim `sub`).
        extra: Дополнительные данные, которые попадут в claim `ctx`.

    Returns:
        tuple[str, int]: JWT и количество секунд до истечения.
    """

    now = datetime.now(tz=UTC)
    expires_in = timedelta(seconds=settings.jwt_ttl_seconds)
    claims = {
        "iss": "rpg-bot-gateway",
        "aud": "rpg-bot-miniapp",
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "jti": uuid4().hex,
        "ctx": extra,
    }
    token = jwt.encode(
        payload=claims,
        key=settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, settings.jwt_ttl_seconds
