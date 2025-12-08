"""Маршруты Gateway API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from ..rate_limit import rate_limit

from ..auth.telegram import InitDataValidationError, InitDataValidator
from ..auth.dependencies import get_current_player, get_data_store
from ..data import DataStoreProtocol, NotFoundError, SceneStateRecord, CampaignRunRecord
from ..config import HealthPayload, Settings, get_settings
from ..jwt_utils import issue_access_token
from ..models import (
    AccessTokenResponse,
    CharacterCreateRequest,
    CharacterPayload,
    CharacterUpdateRequest,
    GenerationRequest,
    CampaignTemplatePayload,
    SceneStatePayload,
    CampaignRunPayload,
    CampaignRunCreateRequest,
    CampaignActionRequest,
    CampaignSummaryResponse,
    MeResponse,
    PartyCreateRequest,
    PartyMemberRequest,
    PartyPayload,
    SceneGenerateRequest,
    SceneGenerateResponse,
    PlayerProfile,
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
from ..domain import CharacterService, PartyService, to_serializable
from ..campaign import CampaignEngine

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


def _character_service(store: DataStoreProtocol) -> CharacterService:
    return CharacterService(store)


def _party_service(store: DataStoreProtocol, character_service: CharacterService) -> PartyService:
    return PartyService(store, character_service)


def _player_profile(record) -> PlayerProfile:
    return PlayerProfile.model_validate(to_serializable(record))


def _character_payload(record) -> CharacterPayload:
    return CharacterPayload.model_validate(to_serializable(record))


def _party_payload(record) -> PartyPayload:
    return PartyPayload.model_validate(to_serializable(record))


def _campaign_engine(request: Request) -> CampaignEngine:
    engine = getattr(request.app.state, "campaign_engine", None)
    if not engine:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Campaign engine unavailable")
    return engine


def _scene_payload(scene: SceneStateRecord | None) -> SceneStatePayload | None:
    if scene is None:
        return None
    return SceneStatePayload.model_validate(to_serializable(scene))


def _run_payload(run: CampaignRunRecord, current_scene: SceneStateRecord | None) -> CampaignRunPayload:
    payload = to_serializable(run)
    payload["current_scene"] = _scene_payload(current_scene)
    return CampaignRunPayload.model_validate(payload)


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


@router.get("/v1/me", response_model=MeResponse, tags=["players"])
def read_me(
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    """Возвращает профиль игрока и список его персонажей."""

    character_service = _character_service(store)
    characters = [_character_payload(c) for c in character_service.list_for_player(player.id)]
    payload = MeResponse(player=_player_profile(player), characters=characters)
    return payload.model_dump(by_alias=True)


@router.get("/v1/characters", tags=["characters"])
def list_characters(
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    items = [_character_payload(c).model_dump(by_alias=True) for c in character_service.list_for_player(player.id)]
    return {"items": items}


@router.post("/v1/characters", tags=["characters"], status_code=status.HTTP_201_CREATED)
def create_character(
    payload: CharacterCreateRequest,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    record = character_service.create(
        player_id=player.id,
        name=payload.name,
        archetype=payload.archetype,
        race=payload.race,
        core_stats=payload.core_stats,
        skills=payload.skills,
    )
    return _character_payload(record).model_dump(by_alias=True)


@router.patch("/v1/characters/{character_id}", tags=["characters"])
def update_character(
    character_id: int,
    payload: CharacterUpdateRequest,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    try:
        character_service.ensure_owner(character_id=character_id, player_id=player.id)
        record = character_service.update(character_id, name=payload.name, archetype=payload.archetype, race=payload.race)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return _character_payload(record).model_dump(by_alias=True)


@router.post("/v1/characters/{character_id}/retire", tags=["characters"])
def retire_character(
    character_id: int,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    try:
        character_service.ensure_owner(character_id=character_id, player_id=player.id)
        record = character_service.retire(character_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return _character_payload(record).model_dump(by_alias=True)


@router.get("/v1/parties", tags=["parties"])
def list_parties(
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    party_service = _party_service(store, character_service)
    items = [_party_payload(p).model_dump(by_alias=True) for p in party_service.list_for_player(player.id)]
    return {"items": items}


@router.post("/v1/parties", tags=["parties"], status_code=status.HTTP_201_CREATED)
def create_party(
    payload: PartyCreateRequest,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    party_service = _party_service(store, character_service)
    try:
        record = party_service.create_party(
            name=payload.name,
            leader_character_id=payload.leader_character_id,
            player_id=player.id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return _party_payload(record).model_dump(by_alias=True)


@router.post("/v1/parties/{party_id}/join", tags=["parties"])
def join_party(
    party_id: int,
    payload: PartyMemberRequest,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    party_service = _party_service(store, character_service)
    try:
        member = party_service.join_party(
            party_id=party_id,
            character_id=payload.character_id,
            player_id=player.id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return {"joinedAt": member.joined_at.isoformat(), "role": member.role, "partyId": member.party_id, "characterId": member.character_id}


@router.post("/v1/parties/{party_id}/leave", tags=["parties"])
def leave_party(
    party_id: int,
    payload: PartyMemberRequest,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    character_service = _character_service(store)
    party_service = _party_service(store, character_service)
    try:
        party_service.leave_party(
            party_id=party_id,
            character_id=payload.character_id,
            player_id=player.id,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return {"left": True}


@router.get("/v1/campaigns", tags=["campaigns"])
def list_campaign_templates(request: Request) -> dict[str, Any]:
    engine = _campaign_engine(request)
    templates = [CampaignTemplatePayload.model_validate(to_serializable(t)).model_dump(by_alias=True) for t in engine.list_templates()]
    return {"items": templates}


@router.post("/v1/campaign-runs", tags=["campaigns"], status_code=status.HTTP_201_CREATED)
def start_campaign_run(
    payload: CampaignRunCreateRequest,
    request: Request,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    engine = _campaign_engine(request)
    character_service = _character_service(store)
    party_service = _party_service(store, character_service)
    try:
        party = party_service.get_party(payload.party_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    party_member_ids = [m.character_id for m in store.list_active_party_members(payload.party_id)]
    requested_characters = payload.character_ids or party_member_ids
    if not requested_characters:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Party has no active members")
    for char_id in requested_characters:
        try:
            character_service.ensure_owner(character_id=char_id, player_id=player.id)
        except PermissionError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    try:
        run, scene = engine.start_run(
            template_id=payload.campaign_template_id,
            party_id=payload.party_id,
            character_ids=requested_characters,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _run_payload(run, scene).model_dump(by_alias=True)


@router.get("/v1/campaign-runs/{run_id}", tags=["campaigns"])
def get_campaign_run(
    run_id: str,
    request: Request,
) -> dict[str, Any]:
    engine = _campaign_engine(request)
    try:
        run, scene = engine.get_state(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _run_payload(run, scene).model_dump(by_alias=True)


@router.post("/v1/campaign-runs/{run_id}/action", tags=["campaigns"])
def apply_campaign_action(
    run_id: str,
    payload: CampaignActionRequest,
    request: Request,
    player=Depends(get_current_player),
    store: DataStoreProtocol = Depends(get_data_store),
) -> dict[str, Any]:
    engine = _campaign_engine(request)
    character_service = _character_service(store)
    try:
        run, _ = engine.get_state(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    party_member_ids = {m.character_id for m in store.list_active_party_members(run.party_id)}
    owned = {c.id for c in character_service.list_for_player(player.id)}
    if not owned.intersection(party_member_ids):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Player not part of this run")

    action = {"type": payload.action_type, "payload": payload.payload, "playerId": player.id}
    try:
        run, scene = engine.apply_action(run_id=run_id, action=action)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CampaignEngine.InvalidPhaseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _run_payload(run, scene).model_dump(by_alias=True)


@router.get("/v1/campaign-runs/{run_id}/summary", tags=["campaigns"])
def get_campaign_summary(
    run_id: str,
    request: Request,
) -> dict[str, Any]:
    engine = _campaign_engine(request)
    try:
        summary = engine.get_summary(run_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    response = CampaignSummaryResponse(
        adventure_summary=summary.summary,
        retcon_package=summary.retcon_package,
    )
    return response.model_dump(by_alias=True)


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
            "display_name": validated.user.username or validated.user.first_name or str(validated.user.id),
            "username": validated.user.username,
        },
    )

    return AccessTokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        issued_at=datetime.now(tz=UTC),
        user=validated.user,
        chat=validated.chat,
    )
