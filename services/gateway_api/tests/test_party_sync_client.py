from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from rpg_gateway_api.party_sync_client import PartySyncClient


def test_party_sync_client_payload(httpx_mock: HTTPXMock) -> None:
    base = "http://party-sync.example"
    client = PartySyncClient(base)
    campaign_id = "run-123"
    payload = {"sceneId": "scene-1", "phase": "SCENE", "status": "SCENE", "outcome": {"result": "success"}}

    httpx_mock.add_response(
        method="POST",
        url=f"{base}/v1/campaigns/{campaign_id}/broadcast",
        json={"ok": True},
    )

    client.broadcast(campaign_id, "campaign.scene_started", payload, trace_id="trace-1")

    request = httpx_mock.get_latest_request()
    assert request is not None
    body = request.json()
    assert body["campaignId"] == campaign_id
    assert body["eventType"] == "campaign.scene_started"
    assert body["sceneId"] == "scene-1"
    assert body["phase"] == "SCENE"
    assert body["status"] == "SCENE"
    assert body["outcome"]["result"] == "success"
    assert body["traceId"] == "trace-1"
