from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rpg_gateway_api.app import create_app
from rpg_gateway_api.config import get_settings


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:ABCDEF")
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    get_settings.cache_clear()


@pytest.fixture
def sample_knowledge_path() -> Path:
    file_path = Path("data/knowledge/sample.yaml").resolve()
    if not file_path.exists():
        pytest.skip("sample knowledge file not found")
    return file_path


def test_knowledge_search_returns_results(monkeypatch: pytest.MonkeyPatch, sample_knowledge_path: Path) -> None:
    monkeypatch.setenv("KNOWLEDGE_SOURCE_PATH", str(sample_knowledge_path))
    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/knowledge/search", params={"q": "moon", "top_k": 2})

    assert response.status_code == 200
    data = response.json()
    assert "items" in data and len(data["items"]) >= 1
    ids = {item["item_id"] for item in data["items"]}
    assert any(item.startswith("scene::") for item in ids)


def test_knowledge_search_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KNOWLEDGE_SOURCE_PATH", raising=False)
    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)

    response = client.get("/v1/knowledge/search", params={"q": "moon"})

    assert response.status_code == 503
