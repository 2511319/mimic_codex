"""Вспомогательные функции для инициализации движка genlayers."""

from __future__ import annotations

import logging
from pathlib import Path

from .exceptions import GenerationError
from .generator import StructuredGenerationEngine
from .loader import load_generation_config
from .providers import LanguageModelProvider, OpenAIResponsesProvider
from .schema_loader import SchemaLoader
from .settings import GenerationSettings

logger = logging.getLogger(__name__)


def create_engine(
    settings: GenerationSettings,
    *,
    provider: LanguageModelProvider | None = None,
) -> StructuredGenerationEngine:
    """Создаёт движок с учётом настроек и выбранного провайдера."""

    profiles_path = _resolve_path(settings.profiles_path)
    schema_root = _resolve_path(settings.schema_root)

    config = load_generation_config(profiles_path)
    schema_loader = SchemaLoader(schema_root)

    lm_provider = provider or _create_provider(settings)

    return StructuredGenerationEngine(
        config=config,
        schema_loader=schema_loader,
        provider=lm_provider,
        max_retries=settings.max_retries,
    )


def _create_provider(settings: GenerationSettings) -> LanguageModelProvider:
    if settings.openai_model is None:
        raise GenerationError("Не указана OpenAI модель для генерации.")
    logger.debug(
        "Инициализация OpenAIResponsesProvider модель=%s timeout=%s",
        settings.openai_model,
        settings.openai_timeout,
    )
    return OpenAIResponsesProvider(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
    )


def _resolve_path(path: Path) -> Path:
    absolute = path if path.is_absolute() else Path.cwd() / path
    return absolute.resolve()
