from __future__ import annotations

import pytest

from rpg_gateway_api.config import get_settings


@pytest.fixture(autouse=True)
def allow_in_memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """Включаем in-memory fallback для unit-тестов по умолчанию."""

    monkeypatch.setenv("DATABASE_FALLBACK_TO_MEMORY", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
