"""Создание приложения FastAPI."""

from __future__ import annotations

import json
import logging
import logging.config
from pathlib import Path

import json
import logging
import logging.config
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi import status
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4

from .api.routes import router
from .data import DataStoreProtocol, InMemoryDataStore, PostgresDataStore
from .campaign import CampaignEngine
from .knowledge import KnowledgeService
from .generation import GenerationService
from .config import get_settings
from .party_sync_client import PartySyncClient
from .party_sync_bus import PartySyncBus, ActionListener, PartySyncNotifier
from .version import __version__
from .observability import setup_observability
from .graph import init_graph_service


def create_app() -> FastAPI:
    """Создаёт и настраивает экземпляр FastAPI.

    Returns:
        FastAPI: Инициализированное приложение с подключёнными маршрутами.
    """

    _setup_logging()
    settings = get_settings()
    app = FastAPI(
        title="RPG-Bot Gateway API",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    setup_observability(app, service_name="gateway-api")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.knowledge_service = KnowledgeService(settings)
    app.state.generation_service = GenerationService(settings)
    app.state.graph_service = init_graph_service(settings)

    data_store: DataStoreProtocol | None = None
    if settings.database_url:
        try:
            data_store = PostgresDataStore(settings.database_url)
        except Exception as exc:  # pragma: no cover - зависит от окружения
            if not settings.database_fallback_to_memory:
                raise
            logging.getLogger(__name__).warning(
                "Postgres недоступен (%s), откатываемся на in-memory", exc
            )
    elif not settings.database_fallback_to_memory:
        raise RuntimeError(
            "DATABASE_URL не задан, а откат на in-memory запрещен (DATABASE_FALLBACK_TO_MEMORY=false)"
        )
    if data_store is None:
        logging.getLogger(__name__).warning(
            "Используется in-memory хранилище (dev/test режим). Укажите DATABASE_URL для Postgres."
        )
        data_store = InMemoryDataStore()
    app.state.data_store = data_store
    party_sync_client = None
    party_sync_bus = None
    notifier = None
    if getattr(settings, "party_sync_redis_url", None):
        party_sync_bus = PartySyncBus(settings.party_sync_redis_url)  # type: ignore[arg-type]
        notifier = PartySyncNotifier(party_sync_bus)
    elif getattr(settings, "party_sync_base_url", None):
        party_sync_client = PartySyncClient(settings.party_sync_base_url)  # type: ignore[arg-type]
        notifier = party_sync_client
    app.state.party_sync_client = party_sync_client
    app.state.party_sync_bus = party_sync_bus
    app.state.campaign_engine = CampaignEngine(app.state.data_store, app.state.generation_service, notifier=notifier)

    @app.middleware("http")
    async def inject_trace_id(request: Request, call_next):  # type: ignore[override]
        """Добавляет `trace_id` в состояние запроса и заголовки ответа.

        Генерирует новый идентификатор, если клиент не передал `X-Request-Id`/`X-Trace-Id`.
        """

        try:
            incoming = request.headers.get("x-trace-id") or request.headers.get("x-request-id")
            trace_id = incoming or uuid4().hex
            request.state.trace_id = trace_id
            response: Response = await call_next(request)
            # Сохраняем след в ответе для последующей корреляции
            response.headers["X-Trace-Id"] = trace_id
            response.headers.setdefault("X-Request-Id", trace_id)
            return response
        except Exception:
            # В случае ошибки middleware возвращаем стандартный ответ, не скрывая первопричину
            return await call_next(request)

    # Единый формат ошибок
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):  # type: ignore[override]
        trace_id = getattr(request.state, "trace_id", "")
        message = _stringify_detail(exc.detail)
        payload = {
            "code": exc.status_code,
            "error": "HTTPException",
            "message": message,
            "traceId": trace_id,
        }
        return Response(content=json.dumps(payload, ensure_ascii=False), status_code=exc.status_code, media_type="application/json")

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):  # type: ignore[override]
        trace_id = getattr(request.state, "trace_id", "")
        payload = {
            "code": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "error": "ValidationError",
            "message": _summarize_validation(exc),
            "traceId": trace_id,
        }
        return Response(content=json.dumps(payload, ensure_ascii=False), status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, media_type="application/json")

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):  # type: ignore[override]
        trace_id = getattr(request.state, "trace_id", "")
        logging.getLogger(__name__).exception("Unhandled error: %s", exc)
        payload = {
            "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "error": "InternalError",
            "message": "Internal Server Error",
            "traceId": trace_id,
        }
        return Response(content=json.dumps(payload, ensure_ascii=False), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, media_type="application/json")

    @app.middleware("http")
    async def http_logger(request: Request, call_next):  # type: ignore[override]
        """Логирует метод, путь, статус и время обработки с traceId."""

        import time as _t

        start = _t.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            try:
                elapsed_ms = int((_t.perf_counter() - start) * 1000)
                trace_id = getattr(request.state, "trace_id", "")
                status_code = response.status_code if response else 500
                logging.getLogger("http").info(
                    "method=%s path=%s status=%s elapsedMs=%s traceId=%s",
                    request.method,
                    request.url.path,
                    status_code,
                    elapsed_ms,
                    trace_id,
                )
            except Exception:
                # не препятствуем ответу при ошибке логирования
                pass
    app.include_router(router)

    @app.on_event("startup")
    async def _start_party_sync_bus() -> None:
        bus = getattr(app.state, "party_sync_bus", None)
        if bus:
            await bus.start()
            listener = ActionListener(bus, app.state.campaign_engine)
            await listener.start()
            app.state.party_action_listener = listener

    @app.on_event("shutdown")
    async def _stop_party_sync_bus() -> None:
        listener = getattr(app.state, "party_action_listener", None)
        if listener:
            await listener.stop()
        bus = getattr(app.state, "party_sync_bus", None)
        if bus:
            await bus.stop()

    @app.get("/config", tags=["system"])
    def read_config_version(request: Request) -> dict[str, str]:
        """Возвращает текущую версию API и состояние подсистем."""

        knowledge_state = "enabled" if app.state.knowledge_service.available else "disabled"
        generation_service = getattr(app.state, "generation_service", None)
        generation_state = "enabled" if generation_service and generation_service.available else "disabled"
        trace_id = getattr(request.state, "trace_id", "")
        return {
            "apiVersion": settings.api_version,
            "knowledge": knowledge_state,
            "generation": generation_state,
            "traceId": trace_id,
        }

    return app


def _setup_logging() -> None:
    """Инициализирует логирование из observability/logging.json, если доступно."""

    try:
        config_path = Path.cwd() / "observability" / "logging.json"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            logging.config.dictConfig(cfg)
    except Exception:
        # Не прерываем запуск приложения из‑за ошибок логирования
        pass


def _stringify_detail(detail: object) -> str:
    try:
        if isinstance(detail, (str, int, float)):
            return str(detail)
        if isinstance(detail, dict) or isinstance(detail, list):
            return json.dumps(detail, ensure_ascii=False)
        return str(detail)
    except Exception:
        return ""


def _summarize_validation(exc: RequestValidationError) -> str:
    try:
        if exc.errors():
            first = exc.errors()[0]
            msg = first.get("msg") or "Validation error"
            loc = first.get("loc")
            if loc:
                return f"{msg} at {'.'.join(str(x) for x in loc)}"
            return str(msg)
        return "Validation error"
    except Exception:
        return "Validation error"
