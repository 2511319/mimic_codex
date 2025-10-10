"""Factory for Party Sync FastAPI application."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .hub import PartyHub
from .version import __version__

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""

    settings = get_settings()
    app = FastAPI(
        title="RPG-Bot Party Sync",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.hub = PartyHub(settings=settings)
    app.include_router(router)

    logger.info("Party Sync service initialised with API version %s", settings.api_version)
    return app
