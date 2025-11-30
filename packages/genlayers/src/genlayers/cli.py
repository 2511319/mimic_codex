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


def _build_settings(
    *,
    config_path: Path | None,
    schema_root: Path | None,
    openai_model: str | None,
    openai_api_key: str | None,
    openai_timeout: float | None,
    max_retries: int | None,
) -> GenerationSettings:
    kwargs: dict[str, Any] = {}
    if config_path is not None:
        kwargs["profiles_path"] = config_path
    if schema_root is not None:
        kwargs["schema_root"] = schema_root
    if openai_model is not None:
        kwargs["openai_model"] = openai_model
    if openai_api_key is not None:
        kwargs["openai_api_key"] = openai_api_key
    if openai_timeout is not None:
        kwargs["openai_timeout"] = openai_timeout
    if max_retries is not None:
        kwargs["max_retries"] = max_retries

    try:
        return GenerationSettings(**kwargs)
    except ValidationError as exc:
        raise typer.BadParameter(f"Некорректные параметры конфигурации: {exc}") from exc


def _read_prompt(prompt: str | None, prompt_file: Path | None) -> str:
    if (prompt is None and prompt_file is None) or (prompt is not None and prompt_file is not None):
        raise typer.BadParameter("Укажите ровно один источник промпта: --prompt или --prompt-file.")
    if prompt is not None:
        return prompt
    assert prompt_file is not None
    try:
        return prompt_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise typer.BadParameter(f"Не удалось прочитать файл промпта: {exc}") from exc


@app.command()
def generate(  # pragma: no cover - CLI интеграционный слой
    profile: str = typer.Argument(..., help="Имя профиля генерации."),
    prompt: str | None = typer.Option(None, "--prompt", help="Промпт в явном виде (строка)."),
    prompt_file: Path | None = typer.Option(None, "--prompt-file", help="Путь к файлу с промптом."),
    config_path: Path | None = typer.Option(
        None,
        "--config",
        help="Путь к YAML-файлу с профилями генерации (GENLAYERS_PROFILES_PATH).",
    ),
    schema_root: Path | None = typer.Option(
        None,
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
    max_retries: int | None = typer.Option(
        None,
        "--max-retries",
        min=0,
        help="Количество повторов при ошибке валидации (GENLAYERS_MAX_RETRIES).",
    ),
) -> None:
    """Генерирует ответ по профилю и выводит результат в stdout."""

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s - %(message)s")
    prompt_text = _read_prompt(prompt, prompt_file)
    settings = _build_settings(
        config_path=config_path,
        schema_root=schema_root,
        openai_model=openai_model,
        openai_api_key=openai_api_key,
        openai_timeout=openai_timeout,
        max_retries=max_retries,
    )

    try:
        engine = create_engine(settings)
        payload = engine.generate(profile, prompt_text)
    except (GenerationError, OSError) as exc:
        logger.error("Генерация завершилась ошибкой: %s", exc)
        raise typer.Exit(code=1) from exc

    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    """Точка входа для python -m genlayers.cli."""

    app()


if __name__ == "__main__":  # pragma: no cover - ручной запуск
    main()
