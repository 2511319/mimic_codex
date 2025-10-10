"""Создание приложения FastAPI."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import get_settings
from .version import __version__


def create_app() -> FastAPI:
    """Создаёт и настраивает экземпляр FastAPI.

    Returns:
        FastAPI: Инициализированное приложение с подключёнными маршрутами.
    """

    settings = get_settings()
    app = FastAPI(
        title="RPG-Bot Gateway API",
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
    app.include_router(router)

    @app.get("/config", tags=["system"])
    def read_config_version() -> dict[str, str]:
        """Возвращает текущую версию API."""

        return {"apiVersion": settings.api_version}

    return app
