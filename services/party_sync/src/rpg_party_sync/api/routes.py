"""API routes for party synchronization service."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status, WebSocket
from pydantic import ValidationError

from ..config import HealthPayload, Settings, get_settings
from ..rate_limit import rate_limit
from ..hub import PartyHub
from ..models import BroadcastAck, BroadcastRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_hub_from_app(app) -> PartyHub:  # type: ignore[no-untyped-def]
    hub = getattr(app.state, "hub", None)
    if hub is None:
        raise RuntimeError("PartyHub is not initialised")
    return hub


def get_hub(request: Request) -> PartyHub:
    """Fetch party hub from HTTP request context."""

    return _get_hub_from_app(request.app)


def get_hub_for_ws(websocket: WebSocket) -> PartyHub:
    """Fetch party hub for WebSocket connections."""

    return _get_hub_from_app(websocket.app)


@router.get("/health", response_model=HealthPayload, tags=["system"])
async def read_health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthPayload:
    """Return service health information."""

    return HealthPayload(status="ok", api_version=settings.api_version)


@router.post(
    "/v1/campaigns/{campaign_id}/broadcast",
    response_model=BroadcastAck,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["broadcast"],
)
async def broadcast_event(
    campaign_id: str,
    request_body: BroadcastRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> BroadcastAck:
    """Broadcast event to all connected peers."""

    hub = get_hub(request)
    deliveries = await hub.broadcast(campaign_id, request_body)
    return BroadcastAck(accepted=True, delivered=deliveries)


@router.websocket("/ws/campaign/{campaign_id}")
async def campaign_ws(
    websocket: WebSocket,
    campaign_id: str,
) -> None:
    """Handle WebSocket connections for campaign updates."""

    hub = get_hub_for_ws(websocket)
    try:
        await hub.handle_connection(campaign_id, websocket)
    except ValidationError as exc:
        logger.warning("Validation error on websocket message: %s", exc)
        await websocket.close(code=1003, reason="Invalid payload")
    except HTTPException as exc:
        logger.warning("HTTP exception inside websocket handler: %s", exc)
        await websocket.close(code=1011, reason="Internal error")
