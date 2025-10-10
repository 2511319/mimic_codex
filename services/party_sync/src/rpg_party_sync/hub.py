"""WebSocket hub for party synchronization."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Dict, Set

from fastapi import WebSocket
from fastapi.websockets import WebSocketDisconnect
from pydantic import ValidationError

from .config import Settings
from .models import BroadcastMessage, HistoryEntry

logger = logging.getLogger(__name__)


class ConnectionLimitError(RuntimeError):
    """Raised when campaign connection limit is exceeded."""


class PartySession:
    """Tracks WebSocket connections and history for a single campaign."""

    def __init__(self, *, settings: Settings) -> None:
        self._settings = settings
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._history: deque[HistoryEntry] = deque(maxlen=settings.broadcast_history_limit)

    async def connect(self, websocket: WebSocket) -> None:
        """Register connection and replay backlog."""

        async with self._lock:
            if len(self._connections) >= self._settings.max_connections_per_campaign:
                raise ConnectionLimitError(
                    f"Too many subscribers for campaign (limit="
                    f"{self._settings.max_connections_per_campaign})"
                )
            self._connections.add(websocket)

        await websocket.accept()
        await self._replay_history(websocket)
        logger.debug("WebSocket joined campaign %s", id(self))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove connection silently."""

        async with self._lock:
            self._connections.discard(websocket)
        logger.debug("WebSocket left campaign %s", id(self))

    async def broadcast(self, message: BroadcastMessage, *, include_sender: bool) -> int:
        """Send message to connected peers and append to history."""

        payload = message.model_dump(by_alias=True)
        deliveries = 0
        async with self._lock:
            self._history.append(HistoryEntry(event=message))
            connections = list(self._connections)

        for connection in connections:
            try:
                if not include_sender and message.sender_id:
                    # Sender filtering is handled by clients; here we broadcast to all.
                    pass
                await connection.send_json(payload)
                deliveries += 1
            except RuntimeError as exc:
                logger.warning("Failed to send payload to client: %s", exc)
                await self._safe_disconnect(connection)
        return deliveries

    async def _safe_disconnect(self, websocket: WebSocket) -> None:
        try:
            await websocket.close()
        except RuntimeError:
            logger.debug("Ignored error while closing websocket", exc_info=True)
        finally:
            await self.disconnect(websocket)

    async def _replay_history(self, websocket: WebSocket) -> None:
        for item in list(self._history):
            try:
                await websocket.send_json(item.event.model_dump(by_alias=True))
            except RuntimeError as exc:
                logger.warning("Failed to replay history: %s", exc)
                break


class PartyHub:
    """Manages campaign sessions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._sessions: Dict[str, PartySession] = {}
        self._lock = asyncio.Lock()

    async def acquire_session(self, campaign_id: str) -> PartySession:
        """Return existing session or create a new one."""

        async with self._lock:
            if campaign_id not in self._sessions:
                self._sessions[campaign_id] = PartySession(settings=self._settings)
            return self._sessions[campaign_id]

    async def handle_connection(self, campaign_id: str, websocket: WebSocket) -> None:
        """Main loop for websocket connection."""

        session = await self.acquire_session(campaign_id)
        try:
            await session.connect(websocket)
        except ConnectionLimitError as exc:
            logger.warning("Connection refused for %s: %s", campaign_id, exc)
            await websocket.close(code=1001, reason="Campaign at capacity")
            return

        try:
            while True:
                data = await websocket.receive_json()
                message = BroadcastMessage.model_validate(data)
                await session.broadcast(message, include_sender=True)
        except WebSocketDisconnect:
            logger.debug("Client disconnected from %s", campaign_id)
        except ValidationError as exc:
            logger.warning("Invalid message on campaign %s: %s", campaign_id, exc)
            await websocket.close(code=1003, reason="Invalid message payload")
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected error in websocket loop: %s", exc)
            await websocket.close(code=1011, reason="Internal error")
        finally:
            await session.disconnect(websocket)

    async def broadcast(self, campaign_id: str, message: BroadcastMessage) -> int:
        """Broadcast message to the campaign."""

        session = await self.acquire_session(campaign_id)
        deliveries = await session.broadcast(message, include_sender=True)
        logger.info(
            "Broadcast event %s to campaign %s for %d receivers",
            message.event_type,
            campaign_id,
            deliveries,
        )
        return deliveries
