"""Загрузчик YAML-конфигураций памяти."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .config import KnowledgeConfig


@lru_cache
def load_knowledge_config(path: str | Path) -> KnowledgeConfig:
    """Загружает конфигурацию `Память37` и валидирует её.

    Args:
        path: Путь к YAML-файлу конфигурации.

    Returns:
        KnowledgeConfig: Проверенная конфигурация доменов знаний.

    Raises:
        FileNotFoundError: Если файл отсутствует.
        ValueError: Если корень YAML не является mapping.
    """

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Knowledge config not found: {file_path}")

    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Knowledge config root must be a mapping")

    return KnowledgeConfig.model_validate(data)
