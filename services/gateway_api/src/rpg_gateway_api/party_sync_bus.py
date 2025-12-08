from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional
from uuid import uuid4

import redis.asyncio as redis

try:  # pragma: no cover - optional
    import fakeredis.aioredis as fakeredis
except Exception:  # pragma: no cover
    fakeredis = None  # type: ignore

logger = logging.getLogger(__name__)

_FAKE_SERVER: Optional[object] = None
if fakeredis:
    _FAKE_SERVER = fakeredis.FakeServer()


class RedisFactory:
    def __init__(self, url: str) -> None:
        self._url = url
        self._client: redis.Redis | None = None

    async def ensure_connected(self) -> None:
        if self._client is None:
            self._client = await self._build_client()

    async def get_client(self) -> redis.Redis:
        if self._client is None:
            await self.ensure_connected()
        assert self._client is not None
        return self._client

    async def close(self) -> None:
        if self._client:
            try:
                await self._client.aclose()
            except Exception:
                logger.debug("Failed to close redis client", exc_info=True)
            self._client = None

    async def _build_client(self) -> redis.Redis:
        if self._url.startswith("fakeredis://"):
            if not fakeredis:
                raise RuntimeError("fakeredis is not installed")
            return fakeredis.FakeRedis(server=_FAKE_SERVER, decode_responses=True)
        return redis.from_url(self._url, decode_responses=True)


class PartySyncBus:
    """Lightweight Redis publisher for party_sync events."""

    def __init__(self, redis_url: str) -> None:
        self._redis_factory = RedisFactory(redis_url)
        self._node_id = uuid4().hex

    async def start(self) -> None:
        await self._redis_factory.ensure_connected()

    async def stop(self) -> None:
        await self._redis_factory.close()

    async def publish(
        self,
        channel: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        trace_id: str | None = None,
        sender_id: str | None = None,
        action_id: str | None = None,
    ) -> None:
        envelope = {
            "eventType": event_type,
            "payload": payload,
            "traceId": trace_id,
            "senderId": sender_id,
            "actionId": action_id,
            "channel": channel,
        }
        redis = await self._redis_factory.get_client()
        await redis.publish(channel, json.dumps({"origin": self._node_id, "message": envelope}))


class ActionListener:
    """Consumes action.request from run:* channels and applies them via CampaignEngine."""

    def __init__(self, bus: PartySyncBus, engine) -> None:  # type: ignore[no-untyped-def]
        self._bus = bus
        self._engine = engine
        self._pubsub = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        redis = await self._bus._redis_factory.get_client()  # pylint: disable=protected-access
        self._pubsub = redis.pubsub()
        await self._pubsub.psubscribe("run:*")
        self._task = asyncio.create_task(self._loop(), name="party-sync-action-listener")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._pubsub:
            try:
                await self._pubsub.close()
            except Exception:
                logger.debug("Failed to close pubsub", exc_info=True)
            self._pubsub = None

    async def _loop(self) -> None:
        assert self._pubsub is not None
        try:
            while True:
                msg = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.02)
                    continue
                await self._handle_message(msg)
        except asyncio.CancelledError:
            raise

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        try:
            decoded = json.loads(msg.get("data"))
        except Exception:
            return
        envelope = decoded.get("message") or {}
        event_type = envelope.get("eventType") or ""
        if not event_type.startswith("action."):
            return
        channel = (envelope.get("channel") or msg.get("channel") or "").decode() if isinstance(msg.get("channel"), bytes) else envelope.get("channel") or msg.get("channel")
        if not channel or not channel.startswith("run:"):
            return
        run_id = channel.split(":", 1)[1]
        payload = envelope.get("payload") or {}
        action = payload.get("action") or payload
        action_id = envelope.get("actionId")
        trace_id = envelope.get("traceId")
        try:
            run, scene = self._engine.apply_action(run_id=run_id, action=action)
        except Exception as exc:  # pragma: no cover - defensive
            await self._bus.publish(channel, "action.error", {"message": str(exc)}, action_id=action_id, trace_id=trace_id)
            return
        await self._publish_state(channel, run_id, run, scene, trace_id=trace_id, action_id=action_id)

    async def _publish_state(self, channel: str, run_id: str, run, scene, *, trace_id: str | None, action_id: str | None) -> None:  # type: ignore[no-untyped-def]
        if scene is None:
            await self._bus.publish(
                channel,
                "scene.update",
                {"sceneId": run.current_scene_id or run_id, "phase": getattr(run, "status", ""), "campaignRunId": run_id},
                trace_id=trace_id,
                action_id=action_id,
            )
            return
        event_type = "combat.update" if getattr(scene, "scene_type", "") == "combat" else "scene.update"
        payload = {
            "sceneId": scene.id,
            "phase": getattr(run, "status", ""),
            "campaignRunId": run_id,
            "sceneType": getattr(scene, "scene_type", None),
            "outcome": getattr(scene, "result_flags", None),
        }
        await self._bus.publish(channel, event_type, payload, trace_id=trace_id, action_id=action_id)
        await self._bus.publish(channel, "action.result", {"actionId": action_id, "status": "applied"}, action_id=action_id, trace_id=trace_id)


class PartySyncNotifier:
    """Adapter for CampaignEngine notifier protocol."""

    def __init__(self, bus: PartySyncBus) -> None:
        self._bus = bus

    def broadcast(self, campaign_id: str, event_type: str, payload: dict[str, Any], trace_id: str | None = None) -> None:
        channel = f"run:{campaign_id}"
        mapped_type = self._map_event(event_type, payload)
        asyncio.create_task(self._bus.publish(channel, mapped_type, payload, trace_id=trace_id))

    def _map_event(self, event_type: str, payload: dict[str, Any]) -> str:
        if event_type.startswith("campaign.scene"):
            scene_type = (payload.get("sceneType") or payload.get("scene_type") or "").lower()
            if scene_type == "combat":
                return "combat.update"
            return "scene.update"
        if event_type.startswith("campaign.phase") or event_type.startswith("campaign.completed"):
            return "scene.update"
        return event_type
