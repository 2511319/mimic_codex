"""Media broker FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .manager import MediaJobManager
from .version import __version__

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    manager = MediaJobManager(settings)
    await manager.start()
    app.state.manager = manager
    try:
        yield
    finally:
        await manager.stop()


def create_app() -> FastAPI:
    """Build FastAPI app with lifespan hooks."""

    settings = get_settings()
    app = FastAPI(
        title="RPG-Bot Media Broker",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    logger.info("Media broker initialised with API version %s", settings.api_version)
    return app
