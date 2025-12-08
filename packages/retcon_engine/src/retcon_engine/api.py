from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException

from .ingestion import RetconIngestService
from .models import CanonPatchRequest, GlobalMetaSnapshot, RetconPackage, WorldEvent
from .repository import RetconRepository
from .scheduler import GlobalTickScheduler

router = APIRouter(prefix="/v1/world", tags=["retcon"])


@lru_cache
def get_repository() -> RetconRepository:
    return RetconRepository()


def get_ingest_service(repo: RetconRepository = Depends(get_repository)) -> RetconIngestService:
    return RetconIngestService(repo)


def get_scheduler(repo: RetconRepository = Depends(get_repository)) -> GlobalTickScheduler:
    return GlobalTickScheduler(repo)


@router.post("/retcon-packages", response_model=list[WorldEvent])
async def ingest_package(
    package: RetconPackage, service: RetconIngestService = Depends(get_ingest_service)
) -> list[WorldEvent]:
    return service.ingest(package)


@router.post("/global-ticks", response_model=GlobalMetaSnapshot)
async def run_global_tick(scheduler: GlobalTickScheduler = Depends(get_scheduler)) -> GlobalMetaSnapshot:
    return await scheduler.run_tick()


@router.get("/canon-candidates")
async def list_candidates(repo: RetconRepository = Depends(get_repository)) -> dict:
    return {"items": repo.list_candidates()}


@router.post("/canon-patches")
async def apply_patch(
    payload: CanonPatchRequest,
    repo: RetconRepository = Depends(get_repository),
) -> dict:
    try:
        patch = repo.apply_patch(
            candidate_id=payload.candidate_id,
            decision=payload.decision,
            applied_by=payload.applied_by,
        )
    except KeyError as exc:  # pragma: no cover - FastAPI handles
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"patch": patch}


__all__ = ["router"]
