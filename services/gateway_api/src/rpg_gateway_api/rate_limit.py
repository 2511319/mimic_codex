"""In-app token bucket rate limiter for FastAPI endpoints.

This lightweight limiter is intended for dev/staging usage without external dependencies.
It limits requests per key (Authorization token or client IP) using a token bucket.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict

from fastapi import HTTPException, Request, status

from .config import get_settings


@dataclass
class _Bucket:
    capacity: float
    refill_rate: float  # tokens per second
    tokens: float
    last_refill: float

    def consume(self, amount: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False


_buckets: Dict[str, _Bucket] = {}
_MAX_KEYS = 10_000


def _key_from_request(request: Request) -> str:
    auth = request.headers.get("authorization") or ""
    if auth:
        return f"auth:{hash(auth)}"
    client = request.client.host if request.client else "unknown"
    return f"ip:{client}"


def rate_limit(request: Request) -> None:
    """Dependency to enforce per-key rate limit using token bucket.

    Args:
        request: FastAPI request object.
        settings: Optional settings (injected for testing); if None, pulls from get_settings().

    Raises:
        HTTPException: with 429 when bucket has no tokens.
    """

    cfg = get_settings()
    if not cfg.rate_limit_enabled:
        return

    key = _key_from_request(request)
    bucket = _buckets.get(key)
    if bucket is None:
        if len(_buckets) >= _MAX_KEYS:
            # crude eviction: drop arbitrary item (not LRU to keep impl minimal)
            _buckets.pop(next(iter(_buckets)), None)
        bucket = _Bucket(
            capacity=float(cfg.rate_limit_burst),
            refill_rate=float(cfg.rate_limit_rps),
            tokens=float(cfg.rate_limit_burst),
            last_refill=time.monotonic(),
        )
        _buckets[key] = bucket

    if not bucket.consume(1.0):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
