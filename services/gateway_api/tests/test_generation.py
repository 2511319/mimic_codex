from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from rpg_gateway_api.app import create_app
from rpg_gateway_api.config import get_settings


class DummyGenerationService:
    def __init__(self, available: bool, result: dict[str, object] | None = None) -> None:
        self.available = available
        self._result = result or {"title": "demo"}
        self._profiles = ["scene.v1", "social.v1"]
        self.calls: list[tuple[str, str]] = []
        self._profiles = ["scene.v1", "social.v1"]

    def generate(self, profile: str, prompt: str) -> dict[str, object]:
        self.calls.append((profile, prompt))
        return self._result

    def profiles(self) -> list[str]:
        return self._profiles

    def profile_detail(self, profile: str) -> dict[str, object]:
        if profile not in self._profiles:
            raise KeyError(profile)
        return {
            "profile": profile,
            "temperature": 0.5,
            "maxOutputTokens": 300,
            "responseSchema": {"type": "object"}
        }

    def profiles(self) -> list[str]:
        return self._profiles


class FailingGenerationService(DummyGenerationService):
    def __init__(self) -> None:
        super().__init__(available=True)

    def generate(self, profile: str, prompt: str):
        raise RuntimeError("engine failure")


@pytest.fixture(autouse=True)
def base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOT_TOKEN", "123456:ABCDEF")
    monkeypatch.setenv("JWT_SECRET", "super-secret-key-123456")
    monkeypatch.setenv("JWT_TTL_SECONDS", "900")
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-nano")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_settings.cache_clear()


def test_generation_returns_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    stub = DummyGenerationService(available=True, result={"title": "Scene"})
    app.state.generation_service = stub
    client = TestClient(app)

    response = client.post("/v1/generation/scene.v1", json={"prompt": "Hello"})

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "scene.v1"
    assert data["result"] == {"title": "Scene"}
    assert stub.calls == [("scene.v1", "Hello")]


def test_generation_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    app.state.generation_service = DummyGenerationService(available=False)
    client = TestClient(app)

    response = client.post("/v1/generation/scene.v1", json={"prompt": "Hello"})

    assert response.status_code == 503


def test_generation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    app.state.generation_service = FailingGenerationService()
    client = TestClient(app)

    response = client.post("/v1/generation/scene.v1", json={"prompt": "Hello"})

    assert response.status_code == 502


def test_generation_profiles(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    service = DummyGenerationService(available=True)
    app.state.generation_service = service
    client = TestClient(app)

    response = client.get("/v1/generation/profiles")

    assert response.status_code == 200
    data = response.json()
    assert data == {"profiles": service.profiles()}


def test_generation_profile_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    service = DummyGenerationService(available=True)
    app.state.generation_service = service
    client = TestClient(app)

    response = client.get("/v1/generation/profiles/scene.v1")

    assert response.status_code == 200
    data = response.json()
    assert data["profile"] == "scene.v1"
    assert data["maxOutputTokens"] == 300


def test_generation_profile_detail_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    service = DummyGenerationService(available=True)
    app.state.generation_service = service
    client = TestClient(app)

    response = client.get("/v1/generation/profiles/unknown")

    assert response.status_code == 404


def test_generation_profiles_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app()
    app.state.generation_service = DummyGenerationService(available=False)
    client = TestClient(app)

    response = client.get("/v1/generation/profiles")

    assert response.status_code == 503
