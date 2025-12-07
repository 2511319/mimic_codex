"""Domain models for party synchronization."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class BroadcastMessage(BaseModel):
    """Envelope for messages distributed to WebSocket listeners."""

    model_config = ConfigDict(populate_by_name=True)

    event_type: str = Field(..., alias="eventType", description="Machine-readable event type.")
    payload: dict[str, Any] = Field(
        ...,
        description="Arbitrary structured payload broadcast to the clients.",
    )
    trace_id: str | None = Field(
        default=None,
        alias="traceId",
        description="Optional trace identifier for observability.",
    )
    sender_id: str | None = Field(
        default=None,
        alias="senderId",
        description="Logical sender (playerId, gmId, service).",
    )


class BroadcastRequest(BaseModel):
    """HTTP request body for broadcast endpoint."""

    model_config = ConfigDict(populate_by_name=True)

    campaign_id: str = Field(..., alias="campaignId")
    message: BroadcastMessage


class BroadcastAck(BaseModel):
    """Acknowledgement response for broadcast operations."""

    accepted: bool = Field(True, description="Indicates that all online peers received the event.")
    delivered: int = Field(..., ge=0, description="Count of receivers the event was sent to.")


class HistoryEntry(BaseModel):
    """Record stored for late subscribers."""

    event: BroadcastMessage
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
