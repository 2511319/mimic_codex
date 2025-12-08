"""Factory for Party Sync FastAPI application."""

from __future__ import annotations

import logging

import json
import logging
import logging.config
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from uuid import uuid4

from .api.routes import router
from .config import get_settings
from .hub import PartyHub
from .version import __version__
from .observability import setup_observability

logger = logging.getLogger(__name__)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    _setup_logging()
    settings = get_settings()
    hub = PartyHub(settings=settings)
    await hub.start()
    app.state.hub = hub
    try:
        yield
    finally:
        await hub.stop()


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    settings = get_settings()
    app = FastAPI(
        title="RPG-Bot Party Sync",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )
    setup_observability(app, service_name="party-sync")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.middleware("http")
    async def inject_trace_id(request: Request, call_next):  # type: ignore[override]
        """Attach `trace_id` to request and response headers for correlation."""

        try:
            incoming = request.headers.get("x-trace-id") or request.headers.get("x-request-id")
            trace_id = incoming or uuid4().hex
            request.state.trace_id = trace_id
            response: Response = await call_next(request)
            response.headers["X-Trace-Id"] = trace_id
            response.headers.setdefault("X-Request-Id", trace_id)
            return response
        except Exception:
            return await call_next(request)

    @app.get("/config", tags=["system"])
    def read_config(request: Request) -> dict[str, str | int]:
        """Return service config snapshot for diagnostics."""

        trace_id = getattr(request.state, "trace_id", "")
        return {
            "apiVersion": settings.api_version,
            "traceId": trace_id,
        }

    @app.middleware("http")
    async def http_logger(request: Request, call_next):  # type: ignore[override]
        """Log method, path, status and elapsedMs with traceId."""

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
                pass

    logger.info("Party Sync service initialised with API version %s", settings.api_version)
    return app


def _setup_logging() -> None:
    """Load JSON logging config if present."""

    try:
        config_path = Path.cwd() / "observability" / "logging.json"
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            logging.config.dictConfig(cfg)
    except Exception:
        pass
