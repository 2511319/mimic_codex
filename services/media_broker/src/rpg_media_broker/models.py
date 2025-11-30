"""Data models for media broker."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MediaJobStatus = Literal["queued", "processing", "succeeded", "failed"]
MediaJobType = Literal["tts", "stt", "image", "avatar"]


class MediaJobRequest(BaseModel):
    """Incoming request to create media job."""

    model_config = ConfigDict(populate_by_name=True)

    job_type: MediaJobType = Field(..., alias="jobType")
    payload: dict[str, Any] = Field(...)
    client_token: str | None = Field(
        default=None,
        alias="clientToken",
        description="Idempotency token supplied by client.",
    )


class MediaJobRecord(BaseModel):
    """Internal representation of media job."""

    job_id: str = Field(..., alias="jobId")
    job_type: MediaJobType = Field(..., alias="jobType")
    payload: dict[str, Any]
    status: MediaJobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc), alias="createdAt")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc), alias="updatedAt")
    client_token: str | None = Field(default=None, alias="clientToken")

    model_config = ConfigDict(populate_by_name=True)


class MediaJobResponse(BaseModel):
    """Response returned to client for GET/POST requests."""

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(..., alias="jobId")
    job_type: MediaJobType = Field(..., alias="jobType")
    status: MediaJobStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")
    client_token: str | None = Field(default=None, alias="clientToken")

    @classmethod
    def from_record(cls, record: MediaJobRecord) -> "MediaJobResponse":
        return cls.model_validate(record.model_dump(by_alias=True))
