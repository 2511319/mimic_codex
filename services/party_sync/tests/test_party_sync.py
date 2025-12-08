from __future__ import annotations

from typing import Iterator

import pytest
from fastapi.testclient import TestClient
import concurrent.futures

from rpg_party_sync.app import create_app
from rpg_party_sync.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_health_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.2.3")
    monkeypatch.setenv("REDIS_URL", "fakeredis://")
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json() == {"status": "ok", "api_version": "1.2.3"}


def test_websocket_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("REDIS_URL", "fakeredis://")
    app = create_app()
    with TestClient(app) as client:
        message = {
            "eventType": "vote_update",
            "payload": {"optionId": "c1", "tally": 2},
            "traceId": "trace-1",
            "senderId": "player:1"
        }

        with client.websocket_connect("/ws/run/cmp1") as ws_a, client.websocket_connect(
            "/ws/run/cmp1"
        ) as ws_b:
            ws_a.send_json(message)
            received = _receive_with_timeout(ws_b)

        assert received["eventType"] == message["eventType"]
        assert received["payload"] == message["payload"]
        assert received["traceId"] == message["traceId"]


def test_history_replay_for_late_subscriber(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_VERSION", "1.0.0")
    monkeypatch.setenv("REDIS_URL", "fakeredis://")
    app = create_app()
    with TestClient(app) as client:
        message = {
            "eventType": "timer_tick",
            "payload": {"secondsLeft": 20}
        }

        with client.websocket_connect("/ws/run/cmp2") as ws_a:
            ws_a.send_json(message)
            _ = _receive_with_timeout(ws_a)

        with client.websocket_connect("/ws/run/cmp2") as ws_late:
            ws_late.send_json(message)
            replay = _receive_with_timeout(ws_late)

        assert replay["eventType"] == "timer_tick"


def _receive_with_timeout(ws, timeout: float = 2.0):  # type: ignore[no-untyped-def]
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = executor.submit(ws.receive_json)
    try:
        return fut.result(timeout=timeout)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
