"""API routes for party synchronization service."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status, WebSocket
from fastapi.websockets import WebSocketDisconnect
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


def _resolve_channel(scope: str, entity_id: str) -> str:
    if scope not in {"party", "run"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported scope")
    return f"{scope}:{entity_id}"


async def _authorize(websocket: WebSocket) -> None:
    settings = get_settings()
    if not settings.ws_api_key:
        return
    auth_header = websocket.headers.get("authorization") or ""
    token = auth_header.split(" ")[-1] if auth_header.lower().startswith("bearer ") else websocket.query_params.get("token")
    if token != settings.ws_api_key:
        await websocket.close(code=4401, reason="Unauthorized")
        raise WebSocketDisconnect()


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
    if request_body.campaign_id != campaign_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="campaignId mismatch",
        )
    message = request_body.message
    if message.trace_id is None:
        trace_id = getattr(request.state, "trace_id", None)
        if trace_id:
            message.trace_id = trace_id
    channel = message.channel or f"run:{campaign_id}"
    deliveries = await hub.publish(channel, message)
    return BroadcastAck(accepted=True, delivered=deliveries)


@router.websocket("/ws/{scope}/{entity_id}")
async def channel_ws(
    websocket: WebSocket,
    scope: str,
    entity_id: str,
) -> None:
    """Handle WebSocket connections for party/run channels."""

    await _authorize(websocket)
    hub = get_hub_for_ws(websocket)
    try:
        channel = _resolve_channel(scope, entity_id)
        await hub.handle_connection(channel, websocket)
    except ValidationError as exc:
        logger.warning("Validation error on websocket message: %s", exc)
        await websocket.close(code=1003, reason="Invalid payload")
    except HTTPException as exc:
        logger.warning("HTTP exception inside websocket handler: %s", exc)
        await websocket.close(code=1011, reason="Internal error")
    except WebSocketDisconnect:
        return


@router.websocket("/ws/campaign/{campaign_id}")
async def legacy_campaign_ws(websocket: WebSocket, campaign_id: str) -> None:
    """Legacy endpoint kept for backward compatibility."""

    await channel_ws(websocket, scope="run", entity_id=campaign_id)
