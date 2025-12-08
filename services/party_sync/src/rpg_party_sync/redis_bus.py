"""Utility for creating Redis/FakeRedis clients."""

from __future__ import annotations

import logging
from typing import Optional

import redis.asyncio as redis

try:  # pragma: no cover - optional in production
    import fakeredis.aioredis as fakeredis
except Exception:  # pragma: no cover
    fakeredis = None  # type: ignore

logger = logging.getLogger(__name__)

_FAKE_SERVER: Optional[object] = None
if fakeredis:
    _FAKE_SERVER = fakeredis.FakeServer()


class RedisFactory:
    """Lazy Redis connector with optional fakeredis backend."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: redis.Redis | None = None

    async def ensure_connected(self) -> None:
        if self._client is not None:
            return
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
