"""Маршруты Gateway API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from ..rate_limit import rate_limit

from ..auth.telegram import InitDataValidationError, InitDataValidator
from ..config import HealthPayload, Settings, get_settings
from ..jwt_utils import issue_access_token
from ..models import (
    AccessTokenResponse,
    GenerationRequest,
    SceneGenerateRequest,
    SceneGenerateResponse,
    TelegramAuthRequest,
)
try:  # optional memory37-graph
    from memory37_graph import SceneGraphContextRequest, KnowledgeVersionRef  # type: ignore
except Exception:  # pragma: no cover
    SceneGraphContextRequest = None  # type: ignore
    KnowledgeVersionRef = None  # type: ignore
from ..graph import init_graph_service
from ..generation import GenerationService
from ..generation_context import GenerationContextBuilder
from ..knowledge import KnowledgeService

router = APIRouter()


def _get_generation_service(request: Request) -> GenerationService:
    service = getattr(request.app.state, "generation_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Generation service unavailable")
    return service


def _get_knowledge_service(request: Request) -> KnowledgeService | None:
    service = getattr(request.app.state, "knowledge_service", None)
    if service and service.available:
        return service
    return None


def _compose_prompt(payload: SceneGenerateRequest, context: str) -> str:
    parts: list[str] = ["[SCENE FRAME]"]
    if payload.campaign_id:
        parts.append(f"campaign_id: {payload.campaign_id}")
    if payload.party_id:
        parts.append(f"party_id: {payload.party_id}")
    if payload.scene_id:
        parts.append(f"scene_id: {payload.scene_id}")
    parts.append("")
    if context:
        parts.append(context)
        parts.append("")
    parts.append("[REQUEST]")
    parts.append(payload.prompt)
    return "\n".join(parts)


async def _generate_with_profile(profile: str, payload: SceneGenerateRequest, request: Request) -> dict[str, Any]:
    generation_service = _get_generation_service(request)
    if profile not in generation_service.profiles():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation profile not found")

    knowledge_service = _get_knowledge_service(request)
    context_builder = GenerationContextBuilder(knowledge_service)
    context, used_items = await context_builder.build_scene_context(payload)
    final_prompt = _compose_prompt(payload, context)

    try:
        result = generation_service.generate(profile, final_prompt)
    except Exception as exc:  # pragma: no cover - тонкая обёртка над движком
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    response = SceneGenerateResponse(
        profile=profile,
        result=result,
        knowledge_items=[item.model_dump() for item in used_items],
    )
    return response.model_dump(by_alias=True)


@router.get("/health", response_model=HealthPayload, tags=["system"])
def read_health(settings: Settings = Depends(get_settings)) -> HealthPayload:
    """Возвращает статус здоровья сервиса."""

    return HealthPayload(status="ok", api_version=settings.api_version)


@router.get("/v1/knowledge/search", tags=["knowledge"])
async def search_knowledge(
    request: Request,
    q: str = Query(..., min_length=2, alias="q"),
    top_k: int = Query(5, ge=1, le=20),
    _rl: None = Depends(rate_limit),
) -> dict[str, list[dict[str, Any]]]:
    """Поиск в базе знаний Memory37."""

    service = getattr(request.app.state, "knowledge_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Knowledge search unavailable")

    results = await service.search(q, top_k=top_k)
    return {"items": [item.model_dump() for item in results]}


@router.get("/v1/graph/scene", tags=["graph"])
def graph_scene_context(
    request: Request,
    scene_id: str = Query(..., min_length=1),
    campaign_id: str = Query("*"),
    party_id: str = Query("*"),
) -> dict[str, Any]:
    """Возвращает графовый контекст сцены (GraphRAG)."""

    service = getattr(request.app.state, "graph_service", None)
    if not service:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG unavailable")

    if SceneGraphContextRequest is None or KnowledgeVersionRef is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG not installed")

    try:
        req = SceneGraphContextRequest(
            scene_id=scene_id,
            campaign_id=campaign_id,
            party_id=party_id,
            version=KnowledgeVersionRef(alias="lore_latest"),
        )
        ctx = service.queries.scene_context(req)
        return {
            "degraded": ctx.degraded,
            "summary": ctx.summary,
            "nodes": ctx.nodes,
            "relations": ctx.relations,
        }
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/v1/graph/npc", tags=["graph"])
def graph_npc_context(
    request: Request,
    npc_id: str = Query(..., min_length=1),
    party_id: str = Query("*"),
) -> dict[str, Any]:
    service = getattr(request.app.state, "graph_service", None)
    if not service:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG unavailable")
    if SceneGraphContextRequest is None or KnowledgeVersionRef is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG not installed")
    try:
        ctx = service.queries.npc_social_context(npc_id, party_id, KnowledgeVersionRef(alias="lore_latest"))
        return {
            "degraded": ctx.degraded,
            "summary": ctx.summary,
            "nodes": ctx.nodes,
            "relations": ctx.relations,
        }
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/v1/graph/quest", tags=["graph"])
def graph_quest_context(
    request: Request,
    quest_id: str = Query(..., min_length=1),
) -> dict[str, Any]:
    service = getattr(request.app.state, "graph_service", None)
    if not service:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG unavailable")
    if SceneGraphContextRequest is None or KnowledgeVersionRef is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG not installed")
    try:
        ctx = service.queries.quest_graph_context(quest_id, KnowledgeVersionRef(alias="lore_latest"))
        return {
            "degraded": ctx.degraded,
            "summary": ctx.summary,
            "nodes": ctx.nodes,
            "relations": ctx.relations,
        }
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/v1/graph/causal", tags=["graph"])
def graph_causal_chain(
    request: Request,
    from_event_id: str = Query(..., min_length=1),
    to_event_id: str | None = Query(None),
    max_hops: int = Query(4, ge=1, le=6),
) -> dict[str, Any]:
    service = getattr(request.app.state, "graph_service", None)
    if not service:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG unavailable")
    if KnowledgeVersionRef is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="GraphRAG not installed")
    try:
        ctx = service.queries.causal_chain(from_event_id, to_event_id, KnowledgeVersionRef(alias="lore_latest"), max_hops=max_hops)
        return {
            "degraded": ctx.degraded,
            "summary": ctx.summary,
            "nodes": ctx.nodes,
            "relations": ctx.relations,
        }
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.post("/v1/generation/{profile}", tags=["generation"])
def generate_content(
    profile: str,
    payload: GenerationRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> dict[str, Any]:
    """Генерация структурированного контента по профилю."""

    service = getattr(request.app.state, "generation_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Generation service unavailable")
    if profile not in service.profiles():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation profile not found")

    try:
        result = service.generate(profile, payload.prompt)
    except Exception as exc:  # pragma: no cover - пробрасываем ошибку наружу
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return {"profile": profile, "result": result}


@router.get("/v1/generation/profiles", tags=["generation"])
def list_generation_profiles(request: Request) -> dict[str, list[str]]:
    """Возвращает список доступных профилей генерации."""

    service = getattr(request.app.state, "generation_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Generation service unavailable")
    return {"profiles": service.profiles()}


@router.get("/v1/generation/profiles/{profile}", tags=["generation"])
def get_generation_profile(profile: str, request: Request) -> dict[str, Any]:
    """Возвращает информацию о профиле генерации."""

    service = getattr(request.app.state, "generation_service", None)
    if not service or not service.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Generation service unavailable")
    try:
        detail = service.profile_detail(profile)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation profile not found") from None
    return detail


@router.post("/v1/generate/scene", tags=["generate"])
async def generate_scene(
    payload: SceneGenerateRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> dict[str, Any]:
    """Доменно ориентированная генерация сцены."""

    return await _generate_with_profile("scene.v1", payload, request)


@router.post("/v1/generate/combat", tags=["generate"])
async def generate_combat(
    payload: SceneGenerateRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> dict[str, Any]:
    """Генерация боевой сцены."""

    return await _generate_with_profile("combat.v1", payload, request)


@router.post("/v1/generate/social", tags=["generate"])
async def generate_social(
    payload: SceneGenerateRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> dict[str, Any]:
    """Генерация социального взаимодействия."""

    return await _generate_with_profile("social.v1", payload, request)


@router.post("/v1/generate/epilogue", tags=["generate"])
async def generate_epilogue(
    payload: SceneGenerateRequest,
    request: Request,
    _rl: None = Depends(rate_limit),
) -> dict[str, Any]:
    """Генерация эпилога."""

    return await _generate_with_profile("epilogue.v1", payload, request)


@router.post(
    "/v1/auth/telegram",
    response_model=AccessTokenResponse,
    tags=["auth"],
    status_code=status.HTTP_200_OK,
)
def exchange_init_data(
    payload: TelegramAuthRequest,
    settings: Settings = Depends(get_settings),
) -> AccessTokenResponse:
    """Обменивает Telegram initData на короткоживущий access token."""

    validator = InitDataValidator(bot_token=settings.bot_token)
    try:
        validated = validator.validate(payload.init_data)
    except InitDataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    access_token, expires_in = issue_access_token(
        settings=settings,
        subject=str(validated.user.id),
        extra={
            "query_id": validated.query_id,
            "chat_id": validated.chat.id if validated.chat else None,
            "language_code": validated.user.language_code,
        },
    )

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        issued_at=datetime.now(tz=UTC),
        user=validated.user,
        chat=validated.chat,
    )
