from __future__ import annotations

import time
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from rpg_media_broker.app import create_app
from rpg_media_broker.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "2.0.0")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "2.0.0"}


def test_job_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("PROCESSING_DELAY_MS", "0")
    app = create_app()

    with TestClient(app) as client:
        payload = {"jobType": "image", "payload": {"prompt": "Ancient ruins"}}
        response = client.post("/v1/media/jobs", json=payload)
        assert response.status_code == 202
        job_id = response.json()["jobId"]

        status = "queued"
        result = None
        for _ in range(20):
            result = client.get(f"/v1/media/jobs/{job_id}")
            status = result.json()["status"]
            if status == "succeeded":
                break
            time.sleep(0.01)

    assert status == "succeeded"
    assert result is not None
    result_payload = result.json()["result"]
    assert result_payload["cdnUrl"].endswith(".webp")


def test_idempotent_submission(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("PROCESSING_DELAY_MS", "0")
    app = create_app()

    with TestClient(app) as client:
        request_body = {
            "jobType": "tts",
            "payload": {"text": "Hello"},
            "clientToken": "token-123"
        }

        resp_first = client.post("/v1/media/jobs", json=request_body)
        resp_second = client.post("/v1/media/jobs", json=request_body)

    assert resp_first.status_code == 202
    assert resp_second.status_code == 202
    assert resp_first.json()["jobId"] == resp_second.json()["jobId"]
