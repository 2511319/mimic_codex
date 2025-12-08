"""FastAPI зависимости для авторизации/игроков."""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status

from rpg_gateway_api.config import Settings, get_settings
from rpg_gateway_api.data import DataStoreProtocol
from rpg_gateway_api.domain import PlayerService


def _extract_token(request: Request) -> str:
    auth_header = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth_header.split(" ", 1)[1]


def get_data_store(request: Request) -> DataStoreProtocol:
    store = getattr(request.app.state, "data_store", None)
    if not store:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Data store unavailable")
    return store


def get_current_player(
    request: Request,
    settings: Settings = Depends(get_settings),
    store: DataStoreProtocol = Depends(get_data_store),
):
    token = _extract_token(request)
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            key=settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience="rpg-bot-miniapp",
            issuer="rpg-bot-gateway",
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing subject")
    try:
        telegram_id = int(sub)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject") from exc
    ctx = payload.get("ctx") or {}
    display_name = ctx.get("display_name") or ctx.get("username") or f"Player-{telegram_id}"

    service = PlayerService(store)
    return service.resolve_player(telegram_id=telegram_id, display_name=display_name)
