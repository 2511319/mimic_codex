"""Клиент для отправки событий в party_sync (опционально)."""

from __future__ import annotations

import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)


class PartySyncClient:
    """Минимальный HTTP-клиент для party_sync.broadcast."""

    def __init__(self, base_url: str, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(timeout=self._timeout)

    def broadcast(self, campaign_id: str, event_type: str, payload: dict[str, Any], trace_id: str | None = None) -> None:
        body = {
            "campaignId": campaign_id,
            "eventType": event_type,
            "sceneId": payload.get("sceneId"),
            "phase": payload.get("phase"),
            "status": payload.get("status"),
            "outcome": payload.get("outcome"),
            "traceId": trace_id,
            "payload": payload,
        }
        url = f"{self._base_url}/v1/campaigns/{campaign_id}/broadcast"
        try:
            resp = self._client.post(url, json=body)
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover - best-effort
            logger.warning("Failed to broadcast to party_sync: %s", exc)
