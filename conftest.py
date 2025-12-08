"""Pytest bootstrap: добавляет локальные src-пакеты в `sys.path`.

Файл нужен для локального запуска тестов без установки пакетов в окружение.
Он модифицирует `sys.path`, указывая на каталоги вида `services/*/src` и
`packages/*/src`, чтобы импорты `rpg_gateway_api`, `rpg_party_sync`,
`rpg_media_broker`, `memory37`, `genlayers`, `rpg_contracts` разрешались.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Iterable


def _extend_sys_path(paths: Iterable[Path]) -> None:
    """Безопасно добавляет директории в `sys.path`.

    Args:
        paths: Итерация путей, которые нужно добавить в начало `sys.path`.
    """

    try:
        for p in paths:
            str_path = str(p)
            if str_path not in sys.path:
                sys.path.insert(0, str_path)
    except Exception:
        # В тестовом bootstrap не используем print; подавляем, чтобы не шуметь.
        # Ошибки импорта будут видны напрямую в падении тестов.
        pass


def _collect_src_paths(root: Path) -> list[Path]:
    """Собирает пути к локальным src-каталогам пакетов.

    Args:
        root: Корень репозитория.

    Returns:
        Список путей к src-каталогам.
    """

    candidates: list[Path] = [
        root / "services" / "gateway_api" / "src",
        root / "services" / "party_sync" / "src",
        root / "services" / "media_broker" / "src",
        root / "packages" / "memory37" / "src",
        root / "packages" / "genlayers" / "src",
        root / "packages" / "rpg_contracts" / "src",
        root / "packages" / "retcon_engine" / "src",
    ]
    return [p for p in candidates if p.exists()]


# Выполняется при импортировании conftest
_extend_sys_path(_collect_src_paths(Path(__file__).parent.resolve()))

