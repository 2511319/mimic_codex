import pytest
from fastapi.testclient import TestClient

import asyncio
import concurrent.futures

import pytest
from fastapi.testclient import TestClient

from rpg_party_sync.app import create_app as create_party_app
from rpg_party_sync.config import get_settings as get_party_settings
from rpg_gateway_api.app import create_app as create_gateway_app
from rpg_gateway_api.config import get_settings as get_gateway_settings
from rpg_gateway_api.campaign.engine import SceneSpec, TemplateSpec
from rpg_gateway_api.data import CampaignTemplateRecord, EpisodeRecord


@pytest.fixture(autouse=True)
def reset_settings() -> None:
    get_party_settings.cache_clear()
    get_gateway_settings.cache_clear()


def test_action_request_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "fakeredis://")
    monkeypatch.setenv("PARTY_SYNC_REDIS_URL", "fakeredis://")
    monkeypatch.setenv("BOT_TOKEN", "stub-token-12345")
    monkeypatch.setenv("JWT_SECRET", "supersecretkey123456")
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("DATABASE_FALLBACK_TO_MEMORY", "true")

    party_app = create_party_app()
    gateway_app = create_gateway_app()
    engine = gateway_app.state.campaign_engine

    template = TemplateSpec(
        record=CampaignTemplateRecord(
            id="demo-template",
            title="Demo",
            description="Demo template",
            season_version="S1",
            metadata={},
        ),
        episode=EpisodeRecord(id="ep1", campaign_template_id="demo-template", order=1, type="main", metadata={}),
        scenes=[SceneSpec(id="s1", title="Scene 1", summary="", scene_type="combat")],
    )
    engine._templates[template.record.id] = template  # type: ignore[attr-defined]

    with TestClient(party_app) as party_client, TestClient(gateway_app):
        run, _ = engine.start_run(template_id=template.record.id, party_id=42, character_ids=[1])
        channel = f"/ws/run/{run.id}"
        with party_client.websocket_connect(channel) as ws_a, party_client.websocket_connect(channel) as ws_b:
            action_event = {
                "eventType": "action.request",
                "payload": {"runId": run.id, "action": {"type": "attack", "value": 5}},
                "actionId": "act-1",
            }
            ws_a.send_json(action_event)
            received_request = _receive_with_timeout(ws_b)
            assert received_request["eventType"] == "action.request"
            result_event = {
                "eventType": "combat.update",
                "payload": {"sceneId": "s1", "phase": "RESOLVE", "campaignRunId": run.id},
                "actionId": "act-1-result",
            }
            ws_a.send_json(result_event)
            update = _receive_with_timeout(ws_b)
            assert update["eventType"] in {"scene.update", "combat.update"}


def _receive_with_timeout(ws, timeout: float = 2.0):  # type: ignore[no-untyped-def]
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    fut = executor.submit(ws.receive_json)
    try:
        return fut.result(timeout=timeout)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
