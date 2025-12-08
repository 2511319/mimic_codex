"""Redis-backed WebSocket hub for party synchronization."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any, Dict, Set
from uuid import uuid4

from fastapi import HTTPException, WebSocket, status
from fastapi.websockets import WebSocketDisconnect
from jsonschema import ValidationError

from .config import Settings
from .models import BroadcastMessage, HistoryEntry
from .redis_bus import RedisFactory
from .schemas import validate_event_envelope

logger = logging.getLogger(__name__)


class ConnectionLimitError(RuntimeError):
    """Raised when a channel connection limit is exceeded."""


class ChannelSession:
    """Tracks WebSocket connections and history for a single channel."""

    def __init__(self, *, channel: str, settings: Settings, redis_factory: RedisFactory, node_id: str) -> None:
        self._settings = settings
        self._channel = channel
        self._redis_factory = redis_factory
        self._node_id = node_id
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._history: deque[HistoryEntry] = deque(maxlen=settings.history_limit)
        self._seen_actions: deque[str] = deque(maxlen=settings.action_dedupe_limit)
        self._pubsub_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._pubsub_task is not None:
            return
        redis = await self._redis_factory.get_client()
        pubsub = redis.pubsub()
        await pubsub.subscribe(self._channel)
        self._pubsub_task = asyncio.create_task(self._consume(pubsub), name=f"channel-listener-{self._channel}")

    async def stop(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
            self._pubsub_task = None

    async def connect(self, websocket: WebSocket) -> None:
        """Register connection and replay backlog."""

        async with self._lock:
            if len(self._connections) >= self._settings.max_connections_per_campaign:
                raise ConnectionLimitError(
                    f"Too many subscribers for channel {self._channel} (limit={self._settings.max_connections_per_campaign})"
                )
            self._connections.add(websocket)

        await websocket.accept()
        await self._replay_history(websocket)
        await self.start()
        logger.debug("WebSocket joined channel=%s", self._channel)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        logger.debug("WebSocket left channel=%s", self._channel)

    def _remember_action(self, action_id: str | None) -> bool:
        if not action_id:
            return True
        if action_id in self._seen_actions:
            return False
        self._seen_actions.append(action_id)
        return True

    async def register_and_broadcast(
        self,
        message: BroadcastMessage,
        *,
        include_sender: bool,
        sender: WebSocket | None = None,
    ) -> int:
        """Send message to connected peers and append to history."""

        if not self._remember_action(message.action_id):
            return 0
        payload = message.model_dump(by_alias=True)
        deliveries = 0
        async with self._lock:
            self._history.append(HistoryEntry(event=message))
            connections = list(self._connections)

        for connection in connections:
            try:
                if not include_sender and sender is not None and connection is sender:
                    continue
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

    async def _consume(self, pubsub) -> None:  # type: ignore[no-untyped-def]
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0.01)
                    continue
                data = message.get("data")
                if not data:
                    continue
                try:
                    decoded = json.loads(data)
                except json.JSONDecodeError:
                    logger.warning("Skip invalid pubsub message for %s", self._channel)
                    continue
                origin = decoded.get("origin")
                if origin == self._node_id:
                    continue
                try:
                    envelope = BroadcastMessage.model_validate(decoded.get("message"))
                except Exception as exc:  # pylint: disable=broad-except
                    logger.warning("Invalid message from pubsub: %s", exc)
                    continue
                await self.register_and_broadcast(envelope, include_sender=True)
        except asyncio.CancelledError:
            logger.debug("Channel listener %s cancelled", self._channel)
            raise
        finally:
            try:
                await pubsub.unsubscribe(self._channel)
                await pubsub.close()
            except Exception:
                pass


class PartyHub:
    """Manages channel sessions backed by Redis pub/sub."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._redis_factory = RedisFactory(settings.redis_url)
        self._sessions: Dict[str, ChannelSession] = {}
        self._lock = asyncio.Lock()
        self._node_id = uuid4().hex

    async def start(self) -> None:
        await self._redis_factory.ensure_connected()

    async def stop(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for session in sessions:
            await session.stop()
        await self._redis_factory.close()

    async def acquire_session(self, channel: str) -> ChannelSession:
        async with self._lock:
            existing = self._sessions.get(channel)
            if existing is not None:
                return existing
            if len(self._sessions) >= self._settings.max_campaigns:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Channel limit reached",
                )
            session = ChannelSession(
                channel=channel,
                settings=self._settings,
                redis_factory=self._redis_factory,
                node_id=self._node_id,
            )
            self._sessions[channel] = session
            return session

    async def handle_connection(self, channel: str, websocket: WebSocket) -> None:
        """Main loop for websocket connection."""

        session = await self.acquire_session(channel)
        try:
            await session.connect(websocket)
        except ConnectionLimitError as exc:
            logger.warning("Connection refused for %s: %s", channel, exc)
            await websocket.close(code=1001, reason="Channel at capacity")
            return

        try:
            while True:
                data = await websocket.receive_json()
                message = BroadcastMessage.model_validate(data)
                message.channel = message.channel or channel
                try:
                    validate_event_envelope(message)
                except ValidationError as exc:
                    logger.warning("Invalid message on channel %s: %s", channel, exc)
                    await websocket.close(code=1003, reason="Invalid payload")
                    return
                await session.register_and_broadcast(message, include_sender=True, sender=websocket)
                await self.publish(channel, message, propagate_local=False)
        except WebSocketDisconnect:
            logger.debug("Client disconnected from %s", channel)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected error in websocket loop: %s", exc)
            await websocket.close(code=1011, reason="Internal error")
        finally:
            await session.disconnect(websocket)
            await self._maybe_cleanup_session(channel, session)

    async def publish(self, channel: str, message: BroadcastMessage, *, propagate_local: bool = True) -> int:
        """Broadcast message to the channel and propagate via Redis."""

        deliveries = 0
        if propagate_local:
            session = await self.acquire_session(channel)
            deliveries = await session.register_and_broadcast(message, include_sender=True)
        payload = json.dumps({"origin": self._node_id, "message": message.model_dump(by_alias=True)})
        try:
            redis = await self._redis_factory.get_client()
            await redis.publish(channel, payload)
        except Exception as exc:  # pragma: no cover - best-effort
            logger.warning("Failed to publish to Redis: %s", exc)
        logger.info(
            "Broadcast event %s to channel %s for %d receivers",
            message.event_type,
            channel,
            deliveries,
        )
        return deliveries

    async def _maybe_cleanup_session(self, channel: str, session: ChannelSession) -> None:
        if session._connections:  # pylint: disable=protected-access
            return
        async with self._lock:
            if not session._connections:
                self._sessions.pop(channel, None)
