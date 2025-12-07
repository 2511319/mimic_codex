"""Сервис генерации контента на базе genlayers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, List

from pydantic import ValidationError

from genlayers import GenerationError as EngineGenerationError
from genlayers import GenerationSettings as EngineSettings
from genlayers import GenerationConfig, StructuredGenerationEngine, create_engine, load_generation_config
from genlayers.schema_loader import SchemaLoader

from .config import Settings

logger = logging.getLogger(__name__)


class GenerationService:
    """Обёртка над движком genlayers для маршрутов Gateway."""

    def __init__(self, settings: Settings) -> None:
        self._engine: StructuredGenerationEngine | None = None
        self._config: GenerationConfig | None = None
        self._schema_loader: SchemaLoader | None = None
        self._available = False
        self._init_engine(settings)

    @property
    def available(self) -> bool:
        return self._available

    def profiles(self) -> List[str]:
        if not self._config:
            return []
        return sorted(self._config.profiles.keys())

    def profile_detail(self, profile: str) -> dict[str, Any]:
        if not self._config or not self._schema_loader:
            raise KeyError("Generation profiles are not available")
        if profile not in self._config.profiles:
            raise KeyError(f"Unknown profile: {profile}")
        profile_cfg = self._config.profiles[profile]
        schema = self._schema_loader.load_schema(profile_cfg.response_schema)
        return {
            "profile": profile,
            "temperature": profile_cfg.temperature,
            "maxOutputTokens": profile_cfg.max_output_tokens,
            "responseSchema": schema,
        }

    def generate(self, profile: str, prompt: str) -> dict[str, Any]:
        if not self._engine:
            raise RuntimeError("Generation service is not configured")
        return self._engine.generate(profile, prompt)

    def _init_engine(self, settings: Settings) -> None:
        api_key = (settings.openai_api_key or "").strip()
        if not api_key or api_key == "***REDACTED***":
            logger.warning("OPENAI_API_KEY не задан, генерация отключена")
            return

        profiles_path = Path(settings.generation_profiles_path)
        schema_root = Path(settings.generation_schema_root)
        if not profiles_path.is_absolute():
            profiles_path = Path.cwd() / profiles_path
        if not schema_root.is_absolute():
            schema_root = Path.cwd() / schema_root

        try:
            engine_settings = EngineSettings(
                profiles_path=profiles_path,
                schema_root=schema_root,
                openai_model=settings.openai_model,
                openai_api_key=settings.openai_api_key,
                openai_timeout=settings.openai_timeout_seconds,
                max_retries=settings.generation_max_retries,
            )
            self._engine = create_engine(engine_settings)
            self._config = load_generation_config(profiles_path)
            self._schema_loader = SchemaLoader(schema_root)
        except (ValidationError, EngineGenerationError, FileNotFoundError) as exc:
            logger.error("Не удалось инициализировать движок генерации: %s", exc)
            self._engine = None
            self._config = None
            self._schema_loader = None
            self._available = False
            return

        self._available = True

