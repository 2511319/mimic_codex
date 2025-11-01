"""Загрузчик JSON Schema для генеративных профилей."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from .exceptions import GenerationError


class SchemaLoader:
    """Загружает JSON Schema из директории contracts/jsonschema."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def load(self, name: str) -> dict[str, Any]:
        """Возвращает схему по имени файла."""

        try:
            return self._load_cached(name)
        except FileNotFoundError as exc:
            raise GenerationError(f"Схема {name} не найдена.", cause=exc) from exc
        except ValueError as exc:
            raise GenerationError(f"Схема {name} имеет некорректный формат.", cause=exc) from exc

    @lru_cache
    def _load_cached(self, name: str) -> dict[str, Any]:
        path = self._base_dir / name
        if not path.exists():
            raise FileNotFoundError(path)
        raw = path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Root schema must be an object.")
        return data
