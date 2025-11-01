"""HTTP API for media broker."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ..config import HealthPayload, Settings, get_settings
from ..manager import MediaJobManager
from ..models import MediaJobRequest, MediaJobResponse
from ..rate_limit import rate_limit

router = APIRouter()


def get_manager(request: Request) -> MediaJobManager:
    manager = getattr(request.app.state, "manager", None)
    if manager is None:
        raise RuntimeError("MediaJobManager is not initialised")
    return manager


@router.get("/health", response_model=HealthPayload, tags=["system"])
async def read_health(settings: Settings = Depends(get_settings)) -> HealthPayload:
    return HealthPayload(status="ok", api_version=settings.api_version)


@router.post(
    "/v1/media/jobs",
    response_model=MediaJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    tags=["jobs"],
)
async def create_job(
    request_body: MediaJobRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> MediaJobResponse:
    manager = get_manager(request)
    record = await manager.enqueue(request_body)
    return MediaJobResponse.from_record(record)


@router.get(
    "/v1/media/jobs/{job_id}",
    response_model=MediaJobResponse,
    tags=["jobs"],
)
async def read_job(job_id: str, request: Request) -> MediaJobResponse:
    manager = get_manager(request)
    try:
        return await manager.as_response(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
