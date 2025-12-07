"""CLI для управления генеративными профилями genlayers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import typer
from pydantic import ValidationError

from .exceptions import GenerationError
from .runtime import create_engine
from .settings import GenerationSettings

logger = logging.getLogger(__name__)

app = typer.Typer(help="Инструменты генеративных профилей genlayers.")


@app.callback()
def main_callback() -> None:
    """Корневой callback, требующий указания команды."""


def _build_settings(
    *,
    profiles_path: Path,
    schema_root: Path,
    openai_model: str | None,
    openai_api_key: str | None,
    openai_timeout: float | None,
    max_retries: int,
) -> GenerationSettings:
    kwargs: dict[str, Any] = {
        "profiles_path": profiles_path,
        "schema_root": schema_root,
        "max_retries": max_retries,
    }
    if openai_model is not None:
        kwargs["openai_model"] = openai_model
    if openai_api_key is not None:
        kwargs["openai_api_key"] = openai_api_key
    if openai_timeout is not None:
        kwargs["openai_timeout"] = openai_timeout
    try:
        return GenerationSettings(**kwargs)
    except ValidationError as exc:
        raise typer.BadParameter(f"Некорректные параметры конфигурации: {exc}") from exc


@app.command(name="generate")
def generate(  # pragma: no cover - CLI интеграционный слой
    profile: str = typer.Option(..., "--profile", help="Имя профиля генерации"),
    prompt: str = typer.Option(..., "--prompt", help="Текст подсказки"),
    profiles_path: Path = typer.Option(
        ...,
        "--profiles-path",
        help="Путь к YAML с профилями генерации (GENLAYERS_PROFILES_PATH).",
    ),
    schema_root: Path = typer.Option(
        ...,
        "--schema-root",
        help="Каталог с JSON Schema ответов (GENLAYERS_SCHEMA_ROOT).",
    ),
    openai_model: str | None = typer.Option(
        None,
        "--openai-model",
        help="Имя модели OpenAI для Responses API (GENLAYERS_OPENAI_MODEL).",
    ),
    openai_api_key: str | None = typer.Option(
        None,
        "--openai-api-key",
        help="Ключ OpenAI (GENLAYERS_OPENAI_API_KEY).",
    ),
    openai_timeout: float | None = typer.Option(
        None,
        "--openai-timeout",
        min=1.0,
        help="Таймаут OpenAI (сек.) (GENLAYERS_OPENAI_TIMEOUT).",
    ),
    max_retries: int = typer.Option(
        2,
        "--max-retries",
        min=0,
        help="Количество повторов при ошибке валидации (GENLAYERS_MAX_RETRIES).",
    ),
) -> None:
    """Генерирует ответ по профилю и выводит результат в stdout."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    settings = _build_settings(
        profiles_path=profiles_path,
        schema_root=schema_root,
        openai_model=openai_model,
        openai_api_key=openai_api_key,
        openai_timeout=openai_timeout,
        max_retries=max_retries,
    )

    try:
        engine = create_engine(settings)
        payload = engine.generate(profile, prompt)
    except (GenerationError, OSError) as exc:
        logger.error("Генерация завершилась ошибкой: %s", exc)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    """Точка входа для python -m genlayers.cli."""

    app()


if __name__ == "__main__":  # pragma: no cover - ручной запуск
    main()
