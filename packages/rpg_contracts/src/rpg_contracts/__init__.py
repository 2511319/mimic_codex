"""Работа с контрактами API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
OPENAPI_PATH = _REPOSITORY_ROOT / "contracts" / "openapi" / "rpg-bot.yaml"


def load_openapi() -> dict[str, Any]:
    """Загружает OpenAPI спецификацию из репозитория.

    Returns:
        dict[str, Any]: Содержимое OpenAPI 3.1 как словарь Python.

    Raises:
        FileNotFoundError: Если спецификация отсутствует в ожидаемом пути.
    """

    if not OPENAPI_PATH.exists():
        raise FileNotFoundError(f"OpenAPI spec not found: {OPENAPI_PATH}")

    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


__all__ = ["load_openapi", "OPENAPI_PATH"]
