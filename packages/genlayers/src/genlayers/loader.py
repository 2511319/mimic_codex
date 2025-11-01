"""Загрузчик конфигурации генеративных профилей."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import GenerationConfig


@lru_cache
def load_generation_config(path: str | Path) -> GenerationConfig:
    """Считывает и валидирует файл профилей генерации.

    Args:
        path: Путь до YAML-файла с описанием профилей.

    Returns:
        GenerationConfig: Валидационная модель конфигурации.

    Raises:
        FileNotFoundError: Если файл отсутствует.
        ValueError: Если структура данных неверна.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Prompt config not found: {file_path}")

    raw = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Prompt config root must be a mapping")

    return GenerationConfig.model_validate(raw)
