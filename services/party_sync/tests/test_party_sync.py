from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from rpg_party_sync.app import create_app
from rpg_party_sync.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.2.3")
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "api_version": "1.2.3"}


def test_websocket_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.0.0")
    app = create_app()
    client = TestClient(app)

    message = {
        "eventType": "vote_update",
        "payload": {"optionId": "c1", "tally": 2},
        "traceId": "trace-1",
        "senderId": "player:1"
    }

    with client.websocket_connect("/ws/campaign/cmp1") as ws_a, client.websocket_connect(
        "/ws/campaign/cmp1"
    ) as ws_b:
        ws_a.send_json(message)
        received = ws_b.receive_json()

    assert received == message


def test_history_replay_for_late_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.0.0")
    app = create_app()
    client = TestClient(app)

    message = {
        "eventType": "timer_tick",
        "payload": {"secondsLeft": 20}
    }

    with client.websocket_connect("/ws/campaign/cmp2") as ws_a:
        ws_a.send_json(message)
        _ = ws_a.receive_json()

    with client.websocket_connect("/ws/campaign/cmp2") as ws_late:
        replay = ws_late.receive_json()

    assert replay == {"eventType": "timer_tick", "payload": {"secondsLeft": 20}, "traceId": None, "senderId": None}
