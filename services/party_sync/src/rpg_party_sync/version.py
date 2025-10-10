"""Version info for party sync service."""

from __future__ import annotations

import importlib.metadata


def _get_version() -> str:
    try:
        return importlib.metadata.version("rpg-bot-monorepo")
    except importlib.metadata.PackageNotFoundError:
        return "0.1.0-dev"


__version__ = _get_version()
